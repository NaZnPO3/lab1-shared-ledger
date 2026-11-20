"""收支记录服务：新增、撤回、修改重提与查询（REQ-005、REQ-006、REQ-007、REQ-011）。

新增与修改都做了两件事：先把请求算成摘要交给幂等执行器（REQ-016），
再用"状态 + 版本号"做乐观锁更新（REQ-017），因此重复点击不会多出记录，
并发修改也只有第一个能成功。
"""

from __future__ import annotations

import sqlite3
from datetime import date

from ..domain.permissions import check_self_scope
from ..domain.state_machine import ensure_transition
from ..domain.validation import RecordInput, validate_record_input
from ..enums import LogAction, Permission, RecordStatus, TxnType
from ..errors import NotFound, StateConflict
from ..models import RecordView, TransactionRecord
from ..timeutil import now, today
from .base import BaseService, new_id
from .idempotency import IdempotencyExecutor, fingerprint


class RecordService(BaseService):
    """收支记录的读写。"""

    # -------------------------------------------------------------- 新增
    def create_record(
        self,
        actor_user_id: str,
        ledger_id: str,
        payload: RecordInput,
        idem_key: str | None = None,
    ) -> TransactionRecord:
        """新增一条待审核记录（REQ-005）。

        Args:
            actor_user_id: 记录人。
            ledger_id: 目标账本。
            payload: 界面提交的数据。
            idem_key: 幂等键；同一键重复提交返回第一次的结果。

        Returns:
            新记录。

        Raises:
            PermissionDenied: 无记录权限（例如只读成员）。
            ValidationError: 字段或金额不合法（REQ-015）。
        """
        member = self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.CREATE_RECORD,
            action=LogAction.CREATE_RECORD,
            target_type="record",
        )
        with self.db.reading() as conn:
            ledger = self.load_ledger(conn, ledger_id)
            period = self.load_open_period(conn, ledger_id)
            categories = self.categories(conn).map_by_id(ledger_id)

        validated = validate_record_input(
            payload,
            amount_limit_cents=ledger.amount_limit_cents,
            categories=categories,
            earliest_date=period.start_date,
            latest_date=today(),
        )

        request_hash = fingerprint(
            {
                "ledger": ledger_id,
                "member": member.member_id,
                "amount": validated.amount_cents,
                "type": validated.txn_type.value,
                "category": validated.category_id,
                "date": validated.occurred_on.isoformat(),
                "note": validated.note,
            }
        )

        def run(conn: sqlite3.Connection) -> str:
            record_id = new_id()
            stamp = now()
            self.records(conn).insert(
                record_id=record_id,
                ledger_id=ledger_id,
                period_id=period.period_id,
                member_id=member.member_id,
                category_id=validated.category_id,
                amount_cents=validated.amount_cents,
                txn_type=validated.txn_type,
                occurred_on=validated.occurred_on,
                note=validated.note,
                status=RecordStatus.PENDING,
                created_at=stamp,
            )
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=actor_user_id,
                member_id=member.member_id,
                action=LogAction.CREATE_RECORD,
                target_type="record",
                target_id=record_id,
                detail=(
                    f"{validated.txn_type.label} {validated.amount_cents / 100:.2f} 元，"
                    f"状态 {RecordStatus.PENDING.label}"
                ),
            )
            return record_id

        record_id, _ = IdempotencyExecutor(self.db).execute(
            user_id=actor_user_id,
            key=idem_key,
            action="create_record",
            request_hash=request_hash,
            run=run,
        )
        with self.db.reading() as conn:
            record = self.records(conn).by_id(record_id)
        if record is None:  # pragma: no cover
            raise NotFound("记录保存失败")
        return record

    # -------------------------------------------------------------- 撤回
    def withdraw_record(self, actor_user_id: str, record_id: str) -> TransactionRecord:
        """原记录人撤回待审核记录（REQ-006）。

        Raises:
            PermissionDenied: 不是原记录人。
            StateConflict: 状态已变化或周期已结算（REQ-025）。
        """
        record = self._load(record_id)
        member = self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.WITHDRAW_OWN_RECORD,
            action=LogAction.WITHDRAW_RECORD,
            target_type="record",
            target_id=record_id,
        )
        check_self_scope(member.member_id, record.member_id)

        with self.db.transaction() as conn:
            current = self.load_record(conn, record_id)
            period = self.periods(conn).by_id(current.period_id)
            if period is not None:
                self.ensure_period_open(period, current)
            ensure_transition(current.status, RecordStatus.WITHDRAWN)
            updated = self.records(conn).update_status(
                record_id=record_id,
                expected_status=current.status,
                new_status=RecordStatus.WITHDRAWN,
                expected_version=current.version,
                updated_at=now(),
            )
            if not updated:
                raise StateConflict("记录已被其他人修改，请刷新后重试")
            self.write_log(
                conn,
                ledger_id=current.ledger_id,
                user_id=actor_user_id,
                member_id=member.member_id,
                action=LogAction.WITHDRAW_RECORD,
                target_type="record",
                target_id=record_id,
                detail=f"撤回记录，状态 {RecordStatus.WITHDRAWN.label}",
            )
            result = self.load_record(conn, record_id)
        return result

    # -------------------------------------------------------------- 修改重提
    def edit_rejected_record(
        self,
        actor_user_id: str,
        record_id: str,
        payload: RecordInput,
    ) -> TransactionRecord:
        """修改被驳回的记录并重新提交（REQ-007）。

        Raises:
            PermissionDenied: 不是原记录人。
            StateConflict: 记录不处于已驳回状态或周期已结算。
        """
        record = self._load(record_id)
        member = self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.EDIT_OWN_RECORD,
            action=LogAction.EDIT_RECORD,
            target_type="record",
            target_id=record_id,
        )
        check_self_scope(member.member_id, record.member_id)

        with self.db.reading() as conn:
            ledger = self.load_ledger(conn, record.ledger_id)
            period = self.load_open_period(conn, record.ledger_id)
            categories = self.categories(conn).map_by_id(record.ledger_id)

        validated = validate_record_input(
            payload,
            amount_limit_cents=ledger.amount_limit_cents,
            categories=categories,
            earliest_date=period.start_date,
            latest_date=today(),
        )

        with self.db.transaction() as conn:
            current = self.load_record(conn, record_id)
            ensure_transition(current.status, RecordStatus.PENDING)
            self.ensure_period_open(period, current)
            updated = self.records(conn).update_content(
                record_id=record_id,
                amount_cents=validated.amount_cents,
                txn_type=validated.txn_type,
                category_id=validated.category_id,
                occurred_on=validated.occurred_on,
                note=validated.note,
                expected_status=current.status,
                expected_version=current.version,
                updated_at=now(),
                new_status=RecordStatus.PENDING,
            )
            if not updated:
                raise StateConflict("记录已被其他人修改，请刷新后重试")
            self.write_log(
                conn,
                ledger_id=current.ledger_id,
                user_id=actor_user_id,
                member_id=member.member_id,
                action=LogAction.EDIT_RECORD,
                target_type="record",
                target_id=record_id,
                detail=f"修改被驳回记录并重新提交，状态 {RecordStatus.PENDING.label}",
            )
            result = self.load_record(conn, record_id)
        return result

    # -------------------------------------------------------------- 查询
    def list_records(
        self,
        actor_user_id: str,
        ledger_id: str,
        *,
        statuses: list[RecordStatus] | None = None,
        member_id: str | None = None,
        category_ids: list[str] | None = None,
        txn_type: TxnType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        amount_min_cents: int | None = None,
        amount_max_cents: int | None = None,
        keyword: str | None = None,
        period_id: str | None = None,
        limit: int | None = None,
    ) -> list[RecordView]:
        """按条件查询记录（REQ-011）。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.records(conn).list_views(
                ledger_id,
                statuses=statuses,
                member_id=member_id,
                category_ids=category_ids,
                txn_type=txn_type,
                date_from=date_from,
                date_to=date_to,
                amount_min_cents=amount_min_cents,
                amount_max_cents=amount_max_cents,
                keyword=keyword,
                period_id=period_id,
                limit=limit,
            )

    def status_counts(self, actor_user_id: str, ledger_id: str) -> dict[str, int]:
        """统计各状态记录数量，供界面显示待办角标。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.records(conn).count_by_status(ledger_id)

    def get_record(self, actor_user_id: str, record_id: str) -> RecordView:
        """读取单条记录（含成员与分类名称）。"""
        record = self._load(record_id)
        self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.CREATE_RECORD,
            target_type="record",
            target_id=record_id,
        )
        with self.db.reading() as conn:
            view = self.records(conn).view_by_id(record_id)
        if view is None:  # pragma: no cover
            raise NotFound("收支记录不存在")
        return view

    # -------------------------------------------------------------- 内部
    def _load(self, record_id: str) -> TransactionRecord:
        """读取记录实体，不存在时抛出 :class:`NotFound`。"""
        with self.db.reading() as conn:
            record = self.records(conn).by_id(record_id)
        if record is None:
            raise NotFound("收支记录不存在")
        return record
