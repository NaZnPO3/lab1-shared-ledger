"""应用服务基类：身份解析、权限检查与操作日志。

所有子服务共用这里的入口，保证：

1. 每次写操作都先解析"当前用户在该账本中的有效成员身份"，退出账本或非成员
   一律拒绝（REQ-003、REQ-004、REQ-020）；
2. 越权请求即使被拒绝也会留下日志，且日志写在独立事务里，不会随业务回滚消失
   （REQ-018、REQ-020）；
3. 日志写入统一走 :meth:`BaseService.write_log`，避免各处格式不一致。
"""

from __future__ import annotations

import sqlite3
import uuid

from ..data.database import Database
from ..data.repositories import (
    CategoryRepository,
    LedgerRepository,
    LogRepository,
    MemberRepository,
    PeriodRepository,
    RecordRepository,
    SettlementRepository,
    UserRepository,
)
from ..enums import LogAction, LogResult, Permission, PeriodStatus
from ..errors import NotFound, PermissionDenied, StateConflict
from ..models import Ledger, Member, SettlementPeriod, TransactionRecord
from ..timeutil import now
from ..domain.permissions import check_permission


def new_id() -> str:
    """生成数据库主键。"""
    return uuid.uuid4().hex


class BaseService:
    """提供仓储构造、身份解析、权限检查与日志写入。"""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------ 仓储构造
    @staticmethod
    def _users(conn: sqlite3.Connection) -> UserRepository:
        """构造用户仓储。"""
        return UserRepository(conn)

    @staticmethod
    def ledgers(conn: sqlite3.Connection) -> LedgerRepository:
        """构造账本仓储。"""
        return LedgerRepository(conn)

    @staticmethod
    def members(conn: sqlite3.Connection) -> MemberRepository:
        """构造成员仓储。"""
        return MemberRepository(conn)

    @staticmethod
    def categories(conn: sqlite3.Connection) -> CategoryRepository:
        """构造分类仓储。"""
        return CategoryRepository(conn)

    @staticmethod
    def periods(conn: sqlite3.Connection) -> PeriodRepository:
        """构造周期仓储。"""
        return PeriodRepository(conn)

    @staticmethod
    def records(conn: sqlite3.Connection) -> RecordRepository:
        """构造记录仓储。"""
        return RecordRepository(conn)

    @staticmethod
    def settlements(conn: sqlite3.Connection) -> SettlementRepository:
        """构造结算仓储。"""
        return SettlementRepository(conn)

    @staticmethod
    def logs(conn: sqlite3.Connection) -> LogRepository:
        """构造日志仓储。"""
        return LogRepository(conn)

    # ------------------------------------------------------------ 读取辅助
    def load_ledger(self, conn: sqlite3.Connection, ledger_id: str) -> Ledger:
        """读取账本，不存在时抛出 :class:`NotFound`。"""
        ledger = self.ledgers(conn).by_id(ledger_id)
        if ledger is None:
            raise NotFound("账本不存在")
        return ledger

    def load_record(self, conn: sqlite3.Connection, record_id: str) -> TransactionRecord:
        """读取收支记录，不存在时抛出 :class:`NotFound`。"""
        record = self.records(conn).by_id(record_id)
        if record is None:
            raise NotFound("收支记录不存在")
        return record

    def load_member(
        self, conn: sqlite3.Connection, ledger_id: str, user_id: str
    ) -> Member:
        """读取用户在该账本中的有效成员身份。

        Raises:
            PermissionDenied: 用户不是成员或已退出该账本。
        """
        member = self.members(conn).by_ledger_and_user(ledger_id, user_id)
        if member is None:
            raise PermissionDenied("你不是该账本的成员")
        if not member.is_active:
            raise PermissionDenied("你已退出该账本，不能再执行该操作")
        return member

    def load_open_period(
        self, conn: sqlite3.Connection, ledger_id: str
    ) -> SettlementPeriod:
        """读取账本当前进行中的结算周期。"""
        period = self.periods(conn).current_open(ledger_id)
        if period is None:
            raise StateConflict("账本当前没有进行中的结算周期")
        return period

    @staticmethod
    def ensure_period_open(
        period: SettlementPeriod, record: TransactionRecord | None = None
    ) -> None:
        """断言周期仍在进行中，结算后周期内的记录不可再改动（REQ-025）。

        Raises:
            StateConflict: 周期已结算时抛出。
        """
        if period.status is not PeriodStatus.OPEN:
            suffix = f"（记录 {record.record_id} 所属周期）" if record else ""
            raise StateConflict(
                f"结算周期已结算{suffix}，该周期的记录只能查询，不能修改"
            )

    # ------------------------------------------------------------ 权限检查
    def authorize(
        self,
        *,
        ledger_id: str,
        user_id: str,
        permission: Permission,
        action: LogAction,
        target_type: str,
        target_id: str | None = None,
    ) -> Member:
        """校验成员身份与角色权限，越权时补写日志并抛出异常（REQ-020）。

        Returns:
            通过校验的成员实体。
        """
        member: Member | None = None
        try:
            with self.db.reading() as conn:
                member = self.load_member(conn, ledger_id, user_id)
            check_permission(member.role, permission)
        except PermissionDenied as exc:
            self.write_denied_log(
                ledger_id=ledger_id,
                user_id=user_id,
                member_id=member.member_id if member else None,
                action=LogAction.UNAUTHORIZED,
                target_type=target_type,
                target_id=target_id,
                detail=f"尝试执行“{action.label}”被拒绝：{exc.message}",
            )
            raise
        return member

    # ------------------------------------------------------------ 日志写入
    def write_log(
        self,
        conn: sqlite3.Connection,
        *,
        ledger_id: str | None,
        user_id: str,
        member_id: str | None,
        action: LogAction,
        target_type: str | None,
        target_id: str | None,
        result: LogResult = LogResult.SUCCESS,
        detail: str = "",
    ) -> str:
        """在给定事务内追加一条操作日志，返回日志 ID。"""
        log_id = new_id()
        self.logs(conn).append(
            log_id=log_id,
            ledger_id=ledger_id,
            actor_user_id=user_id,
            actor_member_id=member_id,
            action=action.value,
            target_type=target_type,
            target_id=target_id,
            result=result.value,
            detail=detail,
            created_at=now(),
        )
        return log_id

    def write_denied_log(
        self,
        *,
        ledger_id: str | None,
        user_id: str,
        member_id: str | None,
        action: LogAction,
        target_type: str | None,
        target_id: str | None,
        detail: str,
    ) -> None:
        """在独立事务中记录一次被拒绝的请求（REQ-018、REQ-020）。"""
        with self.db.transaction() as conn:
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=user_id,
                member_id=member_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                result=LogResult.DENIED,
                detail=detail,
            )
