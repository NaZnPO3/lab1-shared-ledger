"""统计服务（REQ-013）。

统计口径：只统计状态为“已审核”的记录，已驳回、已撤回、已作废和待审核的记录
都不进入统计，这样统计结果总是可以与结算结果对上。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..enums import LogAction, Permission, RecordStatus, TxnType
from ..money import format_cents
from .base import BaseService


@dataclass(frozen=True, slots=True)
class StatRow:
    """一条统计明细。"""

    group_id: str
    group_name: str
    txn_type: TxnType
    count: int
    amount_cents: int

    @property
    def amount_text(self) -> str:
        """金额的可读文本。"""
        return format_cents(self.amount_cents)


@dataclass(frozen=True, slots=True)
class LedgerOverview:
    """账本收支概览。"""

    income_cents: int
    expense_cents: int
    pending_count: int
    record_count: int

    @property
    def net_cents(self) -> int:
        """净收入（收入减支出）。"""
        return self.income_cents - self.expense_cents

    @property
    def income_text(self) -> str:
        """收入合计文本。"""
        return format_cents(self.income_cents)

    @property
    def expense_text(self) -> str:
        """支出合计文本。"""
        return format_cents(self.expense_cents)

    @property
    def net_text(self) -> str:
        """净收入文本。"""
        return format_cents(self.net_cents)


class StatsService(BaseService):
    """按分类、按成员统计收支。"""

    def overview(
        self,
        actor_user_id: str,
        ledger_id: str,
        *,
        period_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> LedgerOverview:
        """汇总账本已审核记录的收支合计。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_STATS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            repository = self.records(conn)
            views = repository.list_views(
                ledger_id,
                statuses=(RecordStatus.APPROVED,),
                period_id=period_id,
                date_from=date_from,
                date_to=date_to,
            )
            counts = repository.count_by_status(ledger_id)

        income = sum(
            view.record.amount_cents
            for view in views
            if view.record.txn_type is TxnType.INCOME
        )
        expense = sum(
            view.record.amount_cents
            for view in views
            if view.record.txn_type is TxnType.EXPENSE
        )
        return LedgerOverview(
            income_cents=income,
            expense_cents=expense,
            pending_count=counts.get(RecordStatus.PENDING.value, 0),
            record_count=len(views),
        )

    def category_stats(
        self,
        actor_user_id: str,
        ledger_id: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[StatRow]:
        """按分类统计已审核记录（REQ-013）。"""
        return self._group(actor_user_id, ledger_id, "category", date_from, date_to)

    def member_stats(
        self,
        actor_user_id: str,
        ledger_id: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[StatRow]:
        """按成员统计已审核记录（REQ-013）。"""
        return self._group(actor_user_id, ledger_id, "member", date_from, date_to)

    def _group(
        self,
        actor_user_id: str,
        ledger_id: str,
        group_by: str,
        date_from: date | None,
        date_to: date | None,
    ) -> list[StatRow]:
        """按指定维度分组统计。

        先取分组汇总，再按日期条件过滤。日期过滤在仓储层用 ``sum_amount``
        不便表达分组，因此这里先粗查再在内存中按条件重新统计一次，
        账本数据量（万级）下足够快，也保持代码可读。
        """
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_STATS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            views = self.records(conn).list_views(
                ledger_id,
                statuses=(RecordStatus.APPROVED,),
                date_from=date_from,
                date_to=date_to,
            )
            names = {
                member.member_id: member.display
                for member in self.members(conn).list_by_ledger(ledger_id)
            }
            categories = {
                item.category_id: item.name
                for item in self.categories(conn).list_by_ledger(ledger_id)
            }

        buckets: dict[tuple[str, TxnType], list[int]] = {}
        for view in views:
            record = view.record
            if group_by == "member":
                key = (names.get(record.member_id, record.member_id), record.txn_type)
            else:
                key = (categories.get(record.category_id, record.category_id), record.txn_type)
            bucket = buckets.setdefault(key, [0, 0])
            bucket[0] += 1
            bucket[1] += record.amount_cents

        rows = [
            StatRow(
                group_id=f"{group_by}:{name}:{txn_type.value}",
                group_name=name,
                txn_type=txn_type,
                count=count,
                amount_cents=amount,
            )
            for (name, txn_type), (count, amount) in buckets.items()
        ]
        rows.sort(key=lambda row: (row.txn_type.value, -row.amount_cents, row.group_name))
        return rows
