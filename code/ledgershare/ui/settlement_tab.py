# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""结算页：预览当前周期、执行结算、查看历史结算。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..domain.permissions import has_permission
from ..enums import PeriodStatus, Permission
from ..money import format_cents, format_cents_signed
from .helpers import FAILED, add_combo_item, confirm, fill_table, guard, make_table

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

LINE_COLUMNS = ("成员", "垫付支出", "应分摊", "应收(+) / 应付(-)")


class SettlementTab(QWidget):
    """周期结算。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._periods: dict[str, object] = {}
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        current_group = QGroupBox("当前结算周期")
        current_layout = QVBoxLayout(current_group)
        self.period_label = QLabel("—")
        self.period_label.setObjectName("hint")
        current_layout.addWidget(self.period_label)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("预览结算")
        self.preview_button.clicked.connect(self.preview_current)
        self.settle_button = QPushButton("执行结算")
        self.settle_button.setObjectName("primary")
        self.settle_button.clicked.connect(self._on_settle)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.settle_button)
        actions.addStretch(1)
        current_layout.addLayout(actions)

        self.preview_table = make_table(LINE_COLUMNS, stretch_column=0)
        current_layout.addWidget(self.preview_table)
        layout.addWidget(current_group, 3)

        history_group = QGroupBox("历史结算")
        history_layout = QVBoxLayout(history_group)
        self.period_combo = QComboBox()
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        history_layout.addWidget(self.period_combo)
        self.history_table = make_table(LINE_COLUMNS, stretch_column=0)
        history_layout.addWidget(self.history_table)
        layout.addWidget(history_group, 2)

        self.hint = QLabel(
            "结算规则：已审核支出由在册成员平均分摊，余数按成员顺序补分；"
            "收入归记录人个人，不参与分摊"
        )
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """刷新周期信息与历史结算。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        user_id = window.user.user_id
        ledger_id = window.ledger.ledger_id

        period = guard(window, window.ctx.ledgers.current_period, user_id, ledger_id)
        if period is not FAILED:
            self.period_label.setText(period.range_text)
            can_settle = bool(
                window.member
                and has_permission(window.member.role, Permission.RUN_SETTLEMENT)
            )
            self.preview_button.setEnabled(can_settle)
            self.settle_button.setEnabled(can_settle)

        periods = guard(window, window.ctx.settlements.list_periods, user_id, ledger_id)
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        self._periods = {}
        if periods is not FAILED:
            for item in periods:
                add_combo_item(self.period_combo, item.range_text, item.period_id)
                self._periods[item.period_id] = item
            settled = [
                index
                for index, item in enumerate(periods)
                if item.status is PeriodStatus.SETTLED
            ]
            if settled:
                self.period_combo.setCurrentIndex(settled[0])
        self.period_combo.blockSignals(False)
        self._on_period_changed()

    def _on_period_changed(self) -> None:
        """切换周期时加载对应结算明细。"""
        period_id = self.period_combo.currentData()
        if not period_id:
            fill_table(self.history_table, [])
            return
        lines = guard(
            self.window,
            self.window.ctx.settlements.list_settlements,
            self.window.user.user_id,
            period_id,
        )
        if lines is FAILED:
            return
        if not lines:
            fill_table(self.history_table, [])
            return
        fill_table(
            self.history_table,
            [self._line_row(line) for line in lines],
            [line.member_id for line in lines],
        )

    @staticmethod
    def _line_row(line) -> tuple[str, ...]:
        """把结算明细转成表格行。"""
        return (
            line.member_name,
            format_cents(line.paid_cents),
            format_cents(line.share_cents),
            format_cents_signed(line.balance_cents),
        )

    # ------------------------------------------------------------------ 动作
    def preview_current(self) -> None:
        window = self.window
        summary = guard(
            window,
            window.ctx.settlements.preview,
            window.user.user_id,
            window.ledger.ledger_id,
        )
        if summary is FAILED:
            return
        fill_table(
            self.preview_table,
            [self._line_row(line) for line in summary.lines],
            [line.member_id for line in summary.lines],
        )
        window.notify(
            f"预览：支出合计 {format_cents(summary.total_expense_cents)} 元，"
            f"收入合计 {format_cents(summary.total_income_cents)} 元"
        )

    def _on_settle(self) -> None:
        window = self.window
        if not confirm(self, "结算后本周期记录将被锁定，只能查询，确定继续吗？"):
            return
        summary = guard(
            window,
            window.ctx.settlements.settle,
            window.user.user_id,
            window.ledger.ledger_id,
        )
        if summary is FAILED:
            return
        fill_table(
            self.preview_table,
            [self._line_row(line) for line in summary.lines],
            [line.member_id for line in summary.lines],
        )
        window.notify("结算完成，已开启下一周期")
        window.refresh_all()
