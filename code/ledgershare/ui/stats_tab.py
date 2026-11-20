# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""统计页：收支概览、按分类统计与按成员统计。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..money import format_cents
from .helpers import FAILED, fill_table, guard, make_table

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

GROUP_COLUMNS = ("名称", "类型", "笔数", "金额（元）")


class StatsTab(QWidget):
    """账本统计视图。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        overview_group = QGroupBox("已审核记录概览")
        overview_layout = QHBoxLayout(overview_group)
        form = QFormLayout()
        self.income_label = QLabel("0.00")
        self.income_label.setObjectName("amount")
        self.expense_label = QLabel("0.00")
        self.expense_label.setObjectName("amount")
        self.net_label = QLabel("0.00")
        self.net_label.setObjectName("amount")
        self.pending_label = QLabel("0")
        form.addRow("收入合计", self.income_label)
        form.addRow("支出合计", self.expense_label)
        form.addRow("净收入", self.net_label)
        form.addRow("待审核记录", self.pending_label)
        overview_layout.addLayout(form)
        overview_layout.addStretch(1)

        refresh_button = QPushButton("刷新统计")
        refresh_button.clicked.connect(self.refresh)
        overview_layout.addWidget(refresh_button)
        layout.addWidget(overview_group)

        tables = QHBoxLayout()

        category_group = QGroupBox("按分类统计")
        category_layout = QVBoxLayout(category_group)
        self.category_table = make_table(GROUP_COLUMNS, stretch_column=0)
        category_layout.addWidget(self.category_table)
        tables.addWidget(category_group)

        member_group = QGroupBox("按成员统计")
        member_layout = QVBoxLayout(member_group)
        self.member_table = make_table(GROUP_COLUMNS, stretch_column=0)
        member_layout.addWidget(self.member_table)
        tables.addWidget(member_group)

        layout.addLayout(tables, 1)

        self.hint = QLabel("统计口径：只统计状态为“已审核”的记录")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """重新拉取统计数据。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        user_id = window.user.user_id
        ledger_id = window.ledger.ledger_id

        overview = guard(window, window.ctx.stats.overview, user_id, ledger_id)
        if overview is not FAILED:
            self.income_label.setText(overview.income_text)
            self.expense_label.setText(overview.expense_text)
            self.net_label.setText(overview.net_text)
            self.pending_label.setText(str(overview.pending_count))

        categories = guard(window, window.ctx.stats.category_stats, user_id, ledger_id)
        if categories is not FAILED:
            fill_table(
                self.category_table,
                [
                    (row.group_name, row.txn_type.label, str(row.count), row.amount_text)
                    for row in categories
                ],
            )

        members = guard(window, window.ctx.stats.member_stats, user_id, ledger_id)
        if members is not FAILED:
            fill_table(
                self.member_table,
                [
                    (row.group_name, row.txn_type.label, str(row.count), row.amount_text)
                    for row in members
                ],
            )

        if overview is not FAILED:
            self.hint.setText(
                "统计口径：只统计状态为“已审核”的记录，"
                f"当前已审核 {overview.record_count} 条，合计 "
                f"{format_cents(overview.income_cents + overview.expense_cents)} 元"
            )
