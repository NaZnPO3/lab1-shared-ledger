"""账本与成员服务（REQ-001、REQ-002、REQ-003、REQ-004、REQ-015、REQ-019）。

账本创建时同时完成三件事：写入创建者成员身份、生成默认分类、开启第一个结算周期，
保证账本一创建就是"可用"状态，界面不需要额外的初始化步骤。
"""

from __future__ import annotations

from ..config import DEFAULT_AMOUNT_LIMIT_CENTS, DEFAULT_CATEGORIES
from ..domain.permissions import check_invite_role, check_role_change
from ..domain.validation import validate_ledger_name
from ..enums import LogAction, MemberStatus, Permission, RecordStatus, Role
from ..errors import (
    DuplicateError,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from ..models import Category, Ledger, Member, SettlementPeriod
from ..money import parse_amount
from ..timeutil import now, today
from .base import BaseService, new_id


class LedgerService(BaseService):
    """账本创建、邀请成员、角色调整与成员退出。"""

    # -------------------------------------------------------------- 创建账本
    def create_ledger(
        self,
        user_id: str,
        name: str,
        amount_limit_cents: int | None = None,
    ) -> Ledger:
        """创建账本，创建者自动成为唯一的所有者（REQ-001）。

        Args:
            user_id: 创建者用户 ID。
            name: 账本名称，允许与其他账本重名。
            amount_limit_cents: 金额上限（分），默认 1e9 元（REQ-015）。

        Returns:
            新建的账本。

        Raises:
            ValidationError: 名称不合法或上限非正数。
            NotFound: 用户不存在。
        """
        ledger_name = validate_ledger_name(name)
        limit = DEFAULT_AMOUNT_LIMIT_CENTS if amount_limit_cents is None else amount_limit_cents
        if limit <= 0:
            raise ValidationError("金额上限必须大于 0")

        created_at = now()
        ledger_id = new_id()
        with self.db.transaction() as conn:
            if self._users(conn).by_id(user_id) is None:
                raise NotFound("用户不存在")
            self.ledgers(conn).insert(
                ledger_id=ledger_id,
                name=ledger_name,
                amount_limit_cents=limit,
                created_by=user_id,
                created_at=created_at,
            )
            owner = self.members(conn)
            owner_member_id = new_id()
            owner.insert(
                member_id=owner_member_id,
                ledger_id=ledger_id,
                user_id=user_id,
                role=Role.OWNER,
                joined_at=created_at,
            )
            self._create_default_categories(conn, ledger_id)
            self.periods(conn).insert(
                period_id=new_id(),
                ledger_id=ledger_id,
                seq=self.ledgers(conn).take_next_period_seq(ledger_id),
                start_date=today(),
            )
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=user_id,
                member_id=owner_member_id,
                action=LogAction.CREATE_LEDGER,
                target_type="ledger",
                target_id=ledger_id,
                detail=f"创建账本“{ledger_name}”，金额上限 {limit // 100} 元",
            )
            ledger = self.ledgers(conn).by_id(ledger_id)
        if ledger is None:  # pragma: no cover - 插入成功后不可能为 None
            raise NotFound("账本创建失败")
        return ledger

    def _create_default_categories(self, conn, ledger_id: str) -> None:
        """写入账本默认分类，避免空分类导致无法记账。"""
        repository = self.categories(conn)
        for name, applies_to in DEFAULT_CATEGORIES:
            repository.insert(
                category_id=new_id(),
                ledger_id=ledger_id,
                name=name,
                applies_to=applies_to,
            )

    # -------------------------------------------------------------- 成员管理
    def invite_member(
        self,
        actor_user_id: str,
        ledger_id: str,
        username: str,
        role: Role = Role.MEMBER,
    ) -> Member:
        """把已注册用户加入账本（REQ-002）。

        管理员可以邀请普通成员和只读成员，创建者还可以邀请管理员；
        已退出的用户重新加入时沿用原成员身份，历史记录继续关联（REQ-019）。

        Raises:
            PermissionDenied: 无邀请权限或拟赋予的角色超出权限。
            NotFound: 账号不存在。
            DuplicateError: 用户已是该账本的在册成员。
        """
        actor = self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.INVITE_MEMBER,
            action=LogAction.INVITE_MEMBER,
            target_type="member",
        )
        check_invite_role(actor.role, role)

        with self.db.transaction() as conn:
            user_row = self._users(conn).by_username(username.strip())
            if user_row is None:
                raise NotFound("账号不存在，请先让对方注册")
            target_user_id = user_row["user_id"]
            repository = self.members(conn)
            existing = repository.by_ledger_and_user(ledger_id, target_user_id)
            stamp = now()
            if existing is None:
                member_id = new_id()
                repository.insert(
                    member_id=member_id,
                    ledger_id=ledger_id,
                    user_id=target_user_id,
                    role=role,
                    joined_at=stamp,
                )
            elif existing.is_active:
                raise DuplicateError("该用户已经是账本成员")
            else:
                member_id = existing.member_id
                repository.reactivate(member_id, role, stamp)
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.INVITE_MEMBER,
                target_type="member",
                target_id=member_id,
                detail=f"邀请 {username} 加入账本，角色 {role.label}",
            )
            member = repository.by_id(member_id)
        if member is None:  # pragma: no cover
            raise NotFound("成员邀请失败")
        return member

    def change_member_role(
        self,
        actor_user_id: str,
        ledger_id: str,
        member_id: str,
        new_role: Role,
    ) -> Member:
        """调整成员角色（REQ-003）。

        Raises:
            PermissionDenied: 越权调整（管理员不能动管理员，创建者角色不可变）。
            NotFound: 目标成员不存在或已退出。
        """
        actor = self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.CHANGE_MEMBER_ROLE,
            action=LogAction.CHANGE_ROLE,
            target_type="member",
            target_id=member_id,
        )
        with self.db.transaction() as conn:
            repository = self.members(conn)
            target = repository.by_id(member_id)
            if target is None or target.ledger_id != ledger_id:
                raise NotFound("成员不存在")
            if not target.is_active:
                raise NotFound("该成员已退出账本")
            check_role_change(actor.role, target.role, new_role)
            repository.update_role(member_id, new_role)
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.CHANGE_ROLE,
                target_type="member",
                target_id=member_id,
                detail=f"{target.display} 的角色由 {target.role.label} 调整为 {new_role.label}",
            )
            updated = repository.by_id(member_id)
        if updated is None:  # pragma: no cover
            raise NotFound("成员不存在")
        return updated

    def leave_ledger(self, user_id: str, ledger_id: str) -> None:
        """成员退出账本（REQ-004、REQ-019）。

        当前结算周期内仍有待审核或已审核记录时不允许退出，必须先完成结算。

        Raises:
            PermissionDenied: 创建者不能退出。
            ValidationError: 存在未结算记录。
        """
        with self.db.transaction() as conn:
            repository = self.members(conn)
            member = self.load_member(conn, ledger_id, user_id)
            if member.role is Role.OWNER:
                raise PermissionDenied("账本创建者不能退出账本")
            period = self.load_open_period(conn, ledger_id)
            pending = self.records(conn).count_in_period_for_member(
                period.period_id,
                member.member_id,
                (RecordStatus.PENDING, RecordStatus.APPROVED),
            )
            if pending:
                raise ValidationError("当前结算周期内仍有未结算记录，请先完成结算再退出")
            repository.mark_left(member.member_id, now())
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=user_id,
                member_id=member.member_id,
                action=LogAction.LEAVE_LEDGER,
                target_type="member",
                target_id=member.member_id,
                detail=f"{member.display} 退出账本",
            )

    # -------------------------------------------------------------- 账本设置
    def set_amount_limit(
        self, actor_user_id: str, ledger_id: str, amount_text: str
    ) -> Ledger:
        """修改账本金额上限（REQ-015）。

        Raises:
            ValidationError: 金额不是正数。
        """
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.EDIT_LEDGER,
            action=LogAction.CREATE_LEDGER,
            target_type="ledger",
            target_id=ledger_id,
        )
        cents = parse_amount(amount_text)
        if cents <= 0:
            raise ValidationError("金额上限必须大于 0")
        with self.db.transaction() as conn:
            self.ledgers(conn).update_amount_limit(ledger_id, cents)
            ledger = self.ledgers(conn).by_id(ledger_id)
        if ledger is None:  # pragma: no cover
            raise NotFound("账本不存在")
        return ledger

    # -------------------------------------------------------------- 查询
    def list_ledgers(self, user_id: str) -> list[Ledger]:
        """列出用户仍参与的账本。"""
        with self.db.reading() as conn:
            return self.ledgers(conn).list_for_user(user_id)

    def list_members(self, actor_user_id: str, ledger_id: str) -> list[Member]:
        """列出账本全部成员（含已退出）。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.INVITE_MEMBER,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.members(conn).list_by_ledger(ledger_id)

    def list_categories(self, actor_user_id: str, ledger_id: str) -> list[Category]:
        """列出账本分类。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.INVITE_MEMBER,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.categories(conn).list_by_ledger(ledger_id)

    def current_period(
        self, actor_user_id: str, ledger_id: str
    ) -> SettlementPeriod:
        """读取当前结算周期。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.SETTLE_PERIOD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.load_open_period(conn, ledger_id)

    def get_member(self, ledger_id: str, user_id: str) -> Member | None:
        """读取当前用户在该账本中的成员身份（不校验在册状态）。"""
        with self.db.reading() as conn:
            return self.members(conn).by_ledger_and_user(ledger_id, user_id)

    def count_members(self, ledger_id: str) -> int:
        """统计账本在册成员数。"""
        with self.db.reading() as conn:
            return self.members(conn).count_active(ledger_id)


__all__ = ["LedgerService", "MemberStatus"]
