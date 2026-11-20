"""审核与更正服务（REQ-008、REQ-009、REQ-010）。

审核通过/驳回/作废都走同一条乐观锁路径：先读状态，推进状态机，
再用"期望状态 + 版本号"更新，更新的行数为 0 即说明状态已被别人改过，
此时抛出 :class:`StateConflict`，两个管理员同时审核同一条记录只有第一个成功。
"""

from __future__ import annotations

import sqlite3

from ..domain.permissions import check_self_scope
from ..domain.state_machine import ensure_transition
from ..domain.validation import RecordInput, validate_record_input
from ..enums import LogAction, Permission, RecordStatus
from ..errors import NotFound, StateConflict, ValidationError
from ..models import TransactionRecord
from ..timeutil import now, today
from .base import BaseService, new_id
from .idempotency import IdempotencyExecutor, fingerprint


class ReviewService(BaseService):
    """管理员审核、驳回、作废，以及原记录人提交更正。"""

    # -------------------------------------------------------------- 审核通过
    def approve(self, actor_user_id: str, record_id: str) -> TransactionRecord:
        """审核通过记录（REQ-008）；若通过的是更正记录，原记录同时作废（REQ-010）。

        Raises:
            PermissionDenied: 不是管理员。
            StateConflict: 状态已变化或周期已结算。
        """
        record = self._load(record_id)
        actor = self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.REVIEW_RECORD,
            action=LogAction.APPROVE_RECORD,
            target_type="record",
            target_id=record_id,
        )
        with self.db.transaction() as conn:
            current = self.load_record(conn, record_id)
            self._ensure_record_writable(conn, current)
            ensure_transition(current.status, RecordStatus.APPROVED)
            self._update_status(conn, current, RecordStatus.APPROVED)

            detail = f"审核通过记录 {record_id}，状态 {RecordStatus.APPROVED.label}"
            if current.corrects_record_id:
                self._void_original(conn, current, actor.member_id, actor_user_id)
                detail = f"审核通过更正记录 {record_id}，原记录已作废"

            self.write_log(
                conn,
                ledger_id=current.ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.APPROVE_RECORD,
                target_type="record",
                target_id=record_id,
                detail=detail,
            )
            return self.load_record(conn, record_id)

    # -------------------------------------------------------------- 审核驳回
    def reject(
        self, actor_user_id: str, record_id: str, reason: str = ""
    ) -> TransactionRecord:
        """审核驳回记录（REQ-008）。

        Raises:
            PermissionDenied: 不是管理员。
            StateConflict: 状态已变化或周期已结算。
        """
        record = self._load(record_id)
        actor = self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.REVIEW_RECORD,
            action=LogAction.REJECT_RECORD,
            target_type="record",
            target_id=record_id,
        )
        note = (reason or "").strip()
        if len(note) > 200:
            raise ValidationError("驳回原因不能超过 200 个字符")

        with self.db.transaction() as conn:
            current = self.load_record(conn, record_id)
            self._ensure_record_writable(conn, current)
            ensure_transition(current.status, RecordStatus.REJECTED)
            self._update_status(conn, current, RecordStatus.REJECTED)
            self.write_log(
                conn,
                ledger_id=current.ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.REJECT_RECORD,
                target_type="record",
                target_id=record_id,
                detail=f"审核驳回，原因：{note or '未填写'}",
            )
            return self.load_record(conn, record_id)

    # -------------------------------------------------------------- 作废
    def void(
        self, actor_user_id: str, record_id: str, reason: str = ""
    ) -> TransactionRecord:
        """作废已审核记录，保留记录本身（REQ-009）。

        Raises:
            PermissionDenied: 不是管理员。
            StateConflict: 记录不处于已审核状态或周期已结算。
        """
        record = self._load(record_id)
        actor = self.authorize(
            ledger_id=record.ledger_id,
            user_id=actor_user_id,
            permission=Permission.VOID_RECORD,
            action=LogAction.VOID_RECORD,
            target_type="record",
            target_id=record_id,
        )
        note = (reason or "").strip()
        with self.db.transaction() as conn:
            current = self.load_record(conn, record_id)
            self._ensure_record_writable(conn, current)
            ensure_transition(current.status, RecordStatus.VOIDED)
            self._update_status(conn, current, RecordStatus.VOIDED)
            self.write_log(
                conn,
                ledger_id=current.ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.VOID_RECORD,
                target_type="record",
                target_id=record_id,
                detail=f"作废记录，原因：{note or '未填写'}",
            )
            return self.load_record(conn, record_id)

    # -------------------------------------------------------------- 提交更正
    def submit_correction(
        self,
        actor_user_id: str,
        original_record_id: str,
        payload: RecordInput,
        idem_key: str | None = None,
    ) -> TransactionRecord:
        """对已审核记录提交更正记录（REQ-010）。

        已审核记录不允许直接修改，更正是一条独立的、指向原记录的新记录；
        管理员审核通过后原记录才变为已作废。

        Raises:
            PermissionDenied: 不是原记录人。
            StateConflict: 原记录不处于已审核状态。
        """
        original = self._load(original_record_id)
        actor = self.authorize(
            ledger_id=original.ledger_id,
            user_id=actor_user_id,
            permission=Permission.CORRECT_OWN_RECORD,
            action=LogAction.SUBMIT_CORRECTION,
            target_type="record",
            target_id=original_record_id,
        )
        check_self_scope(actor.member_id, original.member_id)

        with self.db.reading() as conn:
            ledger = self.load_ledger(conn, original.ledger_id)
            period = self.load_open_period(conn, original.ledger_id)
            categories = self.categories(conn).map_by_id(original.ledger_id)

        validated = validate_record_input(
            payload,
            amount_limit_cents=ledger.amount_limit_cents,
            categories=categories,
            earliest_date=period.start_date,
            latest_date=today(),
        )
        if original.status is not RecordStatus.APPROVED:
            raise StateConflict(
                f"只有已审核的记录可以提交更正，当前状态为“{original.status.label}”"
            )

        request_hash = fingerprint(
            {
                "original": original_record_id,
                "amount": validated.amount_cents,
                "type": validated.txn_type.value,
                "category": validated.category_id,
                "date": validated.occurred_on.isoformat(),
                "note": validated.note,
            }
        )

        def run(conn: sqlite3.Connection) -> str:
            record_id = new_id()
            self.records(conn).insert(
                record_id=record_id,
                ledger_id=original.ledger_id,
                period_id=period.period_id,
                member_id=actor.member_id,
                category_id=validated.category_id,
                amount_cents=validated.amount_cents,
                txn_type=validated.txn_type,
                occurred_on=validated.occurred_on,
                note=validated.note,
                status=RecordStatus.PENDING,
                created_at=now(),
                corrects_record_id=original_record_id,
            )
            self.write_log(
                conn,
                ledger_id=original.ledger_id,
                user_id=actor_user_id,
                member_id=actor.member_id,
                action=LogAction.SUBMIT_CORRECTION,
                target_type="record",
                target_id=record_id,
                detail=f"对记录 {original_record_id} 提交更正，等待审核",
            )
            return record_id

        record_id, _ = IdempotencyExecutor(self.db).execute(
            user_id=actor_user_id,
            key=idem_key,
            action="submit_correction",
            request_hash=request_hash,
            run=run,
        )
        with self.db.reading() as conn:
            record = self.records(conn).by_id(record_id)
        if record is None:  # pragma: no cover
            raise NotFound("更正记录保存失败")
        return record

    # -------------------------------------------------------------- 内部
    def _load(self, record_id: str) -> TransactionRecord:
        """读取记录实体。"""
        with self.db.reading() as conn:
            record = self.records(conn).by_id(record_id)
        if record is None:
            raise NotFound("收支记录不存在")
        return record

    def _ensure_record_writable(self, conn, record: TransactionRecord) -> None:
        """记录所属周期必须仍在进行中（REQ-025）。"""
        period = self.periods(conn).by_id(record.period_id)
        if period is None:  # pragma: no cover - 外键保证存在
            raise NotFound("结算周期不存在")
        self.ensure_period_open(period, record)

    def _update_status(
        self, conn, record: TransactionRecord, target: RecordStatus
    ) -> None:
        """乐观锁更新状态，未命中说明状态已被并发修改（REQ-017）。"""
        updated = self.records(conn).update_status(
            record_id=record.record_id,
            expected_status=record.status,
            new_status=target,
            expected_version=record.version,
            updated_at=now(),
        )
        if not updated:
            raise StateConflict("记录已被其他人处理，请刷新后重试")

    def _void_original(
        self,
        conn,
        correction: TransactionRecord,
        actor_member_id: str,
        actor_user_id: str,
    ) -> None:
        """更正通过后作废原记录（REQ-010）。"""
        if not correction.corrects_record_id:  # pragma: no cover
            return
        original = self.load_record(conn, correction.corrects_record_id)
        ensure_transition(original.status, RecordStatus.VOIDED)
        updated = self.records(conn).update_status(
            record_id=original.record_id,
            expected_status=original.status,
            new_status=RecordStatus.VOIDED,
            expected_version=original.version,
            updated_at=now(),
        )
        if not updated:
            raise StateConflict("原记录状态已变化，请刷新后重试")
        self.write_log(
            conn,
            ledger_id=original.ledger_id,
            user_id=actor_user_id,
            member_id=actor_member_id,
            action=LogAction.APPROVE_CORRECTION,
            target_type="record",
            target_id=original.record_id,
            detail=f"更正记录 {correction.record_id} 通过审核，原记录作废",
        )
