# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""记录页：筛选、查看与对单条记录的操作。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..domain.validation import RecordInput
from ..enums import RecordStatus, TxnType
from ..money import format_cents
from .helpers import (
    FAILED,
    add_combo_item,
    confirm,
    fill_table,
    guard,
    make_table,
    selected_id,
)
from .record_dialog import RecordDialog

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型检查
    from .main_window import MainWindow

COLUMNS = ("日期", "类型", "分类", "金额（元）", "记录人", "备注", "状态")


class RecordsTab(QWidget):
    """账本记录列表。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._views: dict[str, object] = {}
        self._build()

    # ------------------------------------------------------------------ 布局
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(self._build_filters())
        layout.addLayout(self._build_actions())

        self.table = make_table(COLUMNS, stretch_column=5)
        self.table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self.table, 1)

        self.summary = QLabel("共 0 条")
        self.summary.setObjectName("hint")
        layout.addWidget(self.summary)

    def _build_filters(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.status_combo = QComboBox()
        add_combo_item(self.status_combo, "全部状态", None)
        for status in RecordStatus:
            add_combo_item(self.status_combo, status.label, status)
        self.status_combo.currentIndexChanged.connect(self.refresh)

        self.type_combo = QComboBox()
        add_combo_item(self.type_combo, "全部类型", None)
        for txn_type in (TxnType.EXPENSE, TxnType.INCOME):
            add_combo_item(self.type_combo, txn_type.label, txn_type)
        self.type_combo.currentIndexChanged.connect(self.refresh)

        self.member_combo = QComboBox()
        self.member_combo.currentIndexChanged.connect(self.refresh)

        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("备注关键词")
        self.keyword_edit.returnPressed.connect(self.refresh)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(QDate.currentDate())
        self.date_filter = QCheckBox("按日期")

        row.addWidget(self.status_combo)
        row.addWidget(self.type_combo)
        row.addWidget(self.member_combo)
        row.addWidget(self.keyword_edit, 1)
        row.addWidget(self.date_filter)
        row.addWidget(self.date_from)
        row.addWidget(QLabel("至"))
        row.addWidget(self.date_to)
        return row

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.add_button = QPushButton("＋ 记一笔")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._on_add)

        self.withdraw_button = QPushButton("撤回")
        self.withdraw_button.clicked.connect(self._on_withdraw)

        self.edit_button = QPushButton("修改并重提")
        self.edit_button.clicked.connect(self._on_edit)

        self.correct_button = QPushButton("提交更正")
        self.correct_button.clicked.connect(self._on_correct)

        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)

        row.addWidget(self.add_button)
        row.addWidget(self.withdraw_button)
        row.addWidget(self.edit_button)
        row.addWidget(self.correct_button)
        row.addStretch(1)
        row.addWidget(refresh_button)
        return row

    # ------------------------------------------------------------------ 数据
    def refresh_member_filter(self) -> None:
        """重建成员下拉框（成员变动后调用）。"""
        current = self.member_combo.currentData()
        self.member_combo.blockSignals(True)
        self.member_combo.clear()
        add_combo_item(self.member_combo, "全部成员", None)
        for member in self.window.members:
            add_combo_item(self.member_combo, member.display, member.member_id)
        index = self.member_combo.findData(current)
        if index >= 0:
            self.member_combo.setCurrentIndex(index)
        self.member_combo.blockSignals(False)

    def refresh(self) -> None:
        """按当前筛选条件重新加载记录。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        status = self.status_combo.currentData()
        txn_type = self.type_combo.currentData()
        keyword = self.keyword_edit.text().strip()
        date_from = date_to = None
        if self.date_filter.isChecked():
            date_from = self.date_from.date().toPython()
            date_to = self.date_to.date().toPython()

        service = window.ctx.records
        views = guard(
            window,
            service.list_records,
            window.user.user_id,
            window.ledger.ledger_id,
            statuses=[status] if status else None,
            member_id=self.member_combo.currentData(),
            txn_type=txn_type,
            keyword=keyword or None,
            date_from=date_from,
            date_to=date_to,
        )
        if views is FAILED:
            return

        self._views = {view.record.record_id: view for view in views}
        rows = [
            (
                view.record.occurred_on.isoformat(),
                view.record.txn_type.label,
                view.category_name,
                format_cents(view.record.amount_cents),
                view.member_name,
                view.record.note,
                view.record.status.label,
            )
            for view in views
        ]
        fill_table(self.table, rows, [view.record.record_id for view in views])

        total = sum(view.record.amount_cents for view in views)
        self.summary.setText(f"共 {len(views)} 条，金额合计 {format_cents(total)} 元")
        self._update_actions()

    def _selected_view(self):
        """返回选中行对应的记录视图。"""
        record_id = selected_id(self.table)
        if record_id is None:
            return None
        return self._views.get(record_id)

    def _update_actions(self) -> None:
        """按选中记录的状态与归属，决定按钮是否可用。"""
        view = self._selected_view()
        member_id = self.window.member.member_id if self.window.member else None
        is_mine = bool(view and member_id and view.record.member_id == member_id)

        self.withdraw_button.setEnabled(
            bool(is_mine and view.record.status is RecordStatus.PENDING)
        )
        self.edit_button.setEnabled(
            bool(is_mine and view.record.status is RecordStatus.REJECTED)
        )
        self.correct_button.setEnabled(
            bool(is_mine and view.record.status is RecordStatus.APPROVED)
        )
        self.add_button.setEnabled(self.window.member is not None)

    # ------------------------------------------------------------------ 动作
    def _on_add(self) -> None:
        window = self.window
        if window.ledger is None:
            return
        dialog = RecordDialog(self, window.categories)
        if dialog.exec() != RecordDialog.DialogCode.Accepted:
            return
        record = guard(
            window,
            window.ctx.records.create_record,
            window.user.user_id,
            window.ledger.ledger_id,
            dialog.value(),
            idem_key=window.next_request_key("record"),
        )
        if record is FAILED:
            return
        window.notify(f"已提交记录，状态：{record.status.label}")
        window.refresh_all()

    def _on_withdraw(self) -> None:
        view = self._selected_view()
        if view is None or not confirm(self, "确定撤回这条待审核记录吗？"):
            return
        result = guard(
            self.window,
            self.window.ctx.records.withdraw_record,
            self.window.user.user_id,
            view.record.record_id,
        )
        if result is not FAILED:
            self.window.notify("已撤回该记录")
            self.window.refresh_all()

    def _on_edit(self) -> None:
        window = self.window
        view = self._selected_view()
        if view is None:
            return
        initial = RecordInput(
            amount=f"{view.record.amount_cents / 100:.2f}",
            txn_type=view.record.txn_type.value,
            category_id=view.record.category_id,
            occurred_on=view.record.occurred_on.isoformat(),
            note=view.record.note,
        )
        dialog = RecordDialog(
            self, window.categories, title="修改被驳回的记录", initial=initial
        )
        if dialog.exec() != RecordDialog.DialogCode.Accepted:
            return
        result = guard(
            window,
            window.ctx.records.edit_rejected_record,
            window.user.user_id,
            view.record.record_id,
            dialog.value(),
        )
        if result is not FAILED:
            window.notify("已修改并重新提交审核")
            window.refresh_all()

    def _on_correct(self) -> None:
        window = self.window
        view = self._selected_view()
        if view is None:
            return
        categories = window.categories
        initial = RecordInput(
            amount=f"{view.record.amount_cents / 100:.2f}",
            txn_type=view.record.txn_type.value,
            category_id=view.record.category_id,
            occurred_on=view.record.occurred_on.isoformat(),
            note=view.record.note,
        )
        dialog = RecordDialog(self, categories, title="提交更正（原记录审核通过后作废）", initial=initial)
        if dialog.exec() != RecordDialog.DialogCode.Accepted:
            return
        result = guard(
            window,
            window.ctx.review.submit_correction,
            window.user.user_id,
            view.record.record_id,
            dialog.value(),
            idem_key=window.next_request_key("correction"),
        )
        if result is not FAILED:
            window.notify("更正已提交，等待管理员审核")
            window.refresh_all()

    def apply_role(self) -> None:
        """根据当前角色决定"记一笔"是否可用。"""
        self.add_button.setEnabled(self.window.member is not None)


__all__ = ["RecordsTab"]
