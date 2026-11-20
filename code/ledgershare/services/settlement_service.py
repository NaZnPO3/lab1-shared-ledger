"""结算服务（REQ-014、REQ-021、REQ-025）。

结算规则（需求基线里"分摊公式待确认"，这里采用并在 README 中说明的确定规则）：

* 结算范围：当前进行中周期内、状态为"已审核"的记录；
* 支出由全体在册成员平均分摊，除不尽的"分"按成员 ID 顺序依次补 1 分，保证分摊合计等于支出合计；
* 收入归记录人个人，不参与分摊；
* 每位成员的 ``balance = 本人垫付支出 - 本人应分摊支出``，正数为应收、负数为应付，全体相加为 0。

整个结算在一个事务里完成：写结算明细、关闭当前周期、开启下一周期。
任一步失败都整体回滚，并在独立事务中补写"结算失败"日志（REQ-021）。
"""

from __future__ import annotations

from ..enums import LogAction, LogResult, Permission, RecordStatus, TxnType
from ..errors import NotFound, SettlementError
from ..models import SettlementLine, SettlementPeriod, SettlementSummary
from ..timeutil import now, today
from .base import BaseService, new_id


class SettlementService(BaseService):
    """周期结算与结算结果查询。"""

    # -------------------------------------------------------------- 预览
    def preview(self, actor_user_id: str, ledger_id: str) -> SettlementSummary:
        """预览当前周期的结算结果，不写任何数据。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.RUN_SETTLEMENT,
            action=LogAction.SETTLE_PERIOD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            period = self.load_open_period(conn, ledger_id)
            return self._compute(conn, ledger_id, period)

    # -------------------------------------------------------------- 结算
    def settle(self, actor_user_id: str, ledger_id: str) -> SettlementSummary:
        """执行当前周期的结算（REQ-014）。

        Raises:
            PermissionDenied: 不是管理员。
            SettlementError: 存在待审核记录、没有可结算记录或结算过程失败。
            StateConflict: 周期已被其他请求结算。
        """
        actor = self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.RUN_SETTLEMENT,
            action=LogAction.SETTLE_PERIOD,
            target_type="ledger",
            target_id=ledger_id,
        )
        try:
            return self._settle_in_transaction(ledger_id, actor_user_id, actor.member_id)
        except Exception as exc:  # noqa: BLE001 - 任何失败都要留痕后继续抛
            self._log_failure(
                ledger_id, actor_user_id, actor.member_id, str(exc) or "未知错误"
            )
            raise

    def _settle_in_transaction(
        self, ledger_id: str, actor_user_id: str, actor_member_id: str
    ) -> SettlementSummary:
        """在一个事务内完成结算，失败时整体回滚。"""
        with self.db.transaction() as conn:
            period = self.load_open_period(conn, ledger_id)
            pending = self.records(conn).list_in_period(
                period.period_id, (RecordStatus.PENDING,)
            )
            if pending:
                raise SettlementError(
                    f"当前周期还有 {len(pending)} 条待审核记录，请先完成审核再结算"
                )

            summary = self._compute(conn, ledger_id, period)
            if not summary.lines or summary.total_expense_cents == 0:
                raise SettlementError("当前周期没有已审核的支出记录，无需结算")

            stamp = now()
            rows = [
                {
                    "settlement_id": line.settlement_id,
                    "period_id": period.period_id,
                    "ledger_id": ledger_id,
                    "member_id": line.member_id,
                    "paid_cents": line.paid_cents,
                    "share_cents": line.share_cents,
                    "balance_cents": line.balance_cents,
                    "created_at": stamp.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                for line in summary.lines
            ]
            self.settlements(conn).insert_many(rows)

            end_date = today()
            self.periods(conn).mark_settled(period.period_id, end_date, stamp)
            next_period = self._open_next_period(conn, ledger_id, end_date)

            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=actor_user_id,
                member_id=actor_member_id,
                action=LogAction.SETTLE_PERIOD,
                target_type="period",
                target_id=period.period_id,
                detail=(
                    f"完成第 {period.seq} 期结算，支出合计 {summary.total_expense_cents / 100:.2f} 元，"
                    f"已开启第 {next_period.seq} 期"
                ),
            )
            settled = self.periods(conn).by_id(period.period_id)
            lines = self.settlements(conn).list_by_period(period.period_id)

        if settled is None:  # pragma: no cover
            raise NotFound("结算周期不存在")
        return SettlementSummary(
            period=settled,
            lines=tuple(lines),
            total_expense_cents=summary.total_expense_cents,
            total_income_cents=summary.total_income_cents,
        )

    def _open_next_period(self, conn, ledger_id: str, start_date) -> SettlementPeriod:
        """关闭当前周期后开启下一周期（账本整体继续可用，REQ-025）。"""
        seq = self.ledgers(conn).take_next_period_seq(ledger_id)
        period_id = new_id()
        self.periods(conn).insert(
            period_id=period_id,
            ledger_id=ledger_id,
            seq=seq,
            start_date=start_date,
        )
        next_period = self.periods(conn).by_id(period_id)
        if next_period is None:  # pragma: no cover
            raise NotFound("新结算周期创建失败")
        return next_period

    def _log_failure(
        self, ledger_id: str, actor_user_id: str, actor_member_id: str, reason: str
    ) -> None:
        """在独立事务中记录结算失败原因与操作人（REQ-021）。"""
        with self.db.transaction() as conn:
            self.write_log(
                conn,
                ledger_id=ledger_id,
                user_id=actor_user_id,
                member_id=actor_member_id,
                action=LogAction.SETTLE_FAILED,
                target_type="ledger",
                target_id=ledger_id,
                result=LogResult.FAILED,
                detail=f"结算失败：{reason}",
            )

    # -------------------------------------------------------------- 计算
    def _compute(self, conn, ledger_id: str, period: SettlementPeriod) -> SettlementSummary:
        """计算某周期的结算明细（纯函数式，不写库）。"""
        records = self.records(conn).list_in_period(
            period.period_id, (RecordStatus.APPROVED,)
        )
        total_expense = sum(
            record.amount_cents
            for record in records
            if record.txn_type is TxnType.EXPENSE
        )
        total_income = sum(
            record.amount_cents
            for record in records
            if record.txn_type is TxnType.INCOME
        )

        paid: dict[str, int] = {}
        for record in records:
            if record.txn_type is TxnType.EXPENSE:
                paid[record.member_id] = paid.get(record.member_id, 0) + record.amount_cents

        active = self.members(conn).list_active(ledger_id)
        participant_ids = [member.member_id for member in active]
        for member_id in paid:
            if member_id not in participant_ids:
                participant_ids.append(member_id)
        participant_ids = sorted(set(participant_ids))

        if not participant_ids:
            return SettlementSummary(period=period)

        shares = self._split_evenly(total_expense, participant_ids)
        names = {
            member.member_id: member.display
            for member in self.members(conn).list_by_ledger(ledger_id)
        }

        lines = tuple(
            SettlementLine(
                settlement_id=new_id(),
                period_id=period.period_id,
                ledger_id=ledger_id,
                member_id=member_id,
                paid_cents=paid.get(member_id, 0),
                share_cents=shares[member_id],
                balance_cents=paid.get(member_id, 0) - shares[member_id],
                member_name=names.get(member_id, member_id),
            )
            for member_id in participant_ids
        )
        return SettlementSummary(
            period=period,
            lines=lines,
            total_expense_cents=total_expense,
            total_income_cents=total_income,
        )

    @staticmethod
    def _split_evenly(total_cents: int, member_ids: list[str]) -> dict[str, int]:
        """把金额平均分摊，余数按成员 ID 顺序补分，保证合计精确相等。"""
        if not member_ids:
            return {}
        base, remainder = divmod(total_cents, len(member_ids))
        shares = {member_id: base for member_id in member_ids}
        for member_id in member_ids[:remainder]:
            shares[member_id] += 1
        return shares

    # -------------------------------------------------------------- 查询
    def list_settlements(
        self, actor_user_id: str, period_id: str
    ) -> list[SettlementLine]:
        """读取某周期的结算明细。"""
        with self.db.reading() as conn:
            period = self.periods(conn).by_id(period_id)
            if period is None:
                raise NotFound("结算周期不存在")
            self.authorize(
                ledger_id=period.ledger_id,
                user_id=actor_user_id,
                permission=Permission.VIEW_STATS,
                action=LogAction.SETTLE_PERIOD,
                target_type="period",
                target_id=period_id,
            )
            return self.settlements(conn).list_by_period(period_id)

    def list_periods(
        self, actor_user_id: str, ledger_id: str
    ) -> list[SettlementPeriod]:
        """列出账本的全部结算周期。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_RECORDS,
            action=LogAction.SETTLE_PERIOD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.periods(conn).list_by_ledger(ledger_id)
