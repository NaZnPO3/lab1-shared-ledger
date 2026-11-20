# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""记账 / 更正对话框。"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..domain.validation import RecordInput
from ..enums import TxnType
from ..models import Category
from .helpers import combo_enum


class RecordDialog(QDialog):
    """收集一条收支记录的字段。

    这里只做"字段是否填全"的界面级检查，金额上限、分类与收支类型是否匹配等
    业务规则仍由服务层校验，避免两处规则不一致。
    """

    def __init__(
        self,
        parent: QWidget | None,
        categories: list[Category],
        *,
        title: str = "新增记录",
        initial: RecordInput | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._categories = categories
        self._initial = initial
        self._build()
        self._populate_categories()
        self._apply_initial()

    # ------------------------------------------------------------------ 布局
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.type_combo = QComboBox()
        for txn_type in (TxnType.EXPENSE, TxnType.INCOME):
            self.type_combo.addItem(txn_type.label, txn_type)
        self.type_combo.currentIndexChanged.connect(self._populate_categories)

        self.category_combo = QComboBox()

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("例如 128.50，最多两位小数")

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setMaximumDate(QDate.currentDate())

        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("备注（可选）")
        self.note_edit.setFixedHeight(64)

        form.addRow("收支类型", self.type_combo)
        form.addRow("分类", self.category_combo)
        form.addRow("金额（元）", self.amount_edit)
        form.addRow("发生日期", self.date_edit)
        form.addRow("备注", self.note_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_categories(self) -> None:
        """按当前收支类型过滤可选分类。"""
        txn_type = combo_enum(self.type_combo, TxnType)
        self.category_combo.clear()
        for category in self._categories:
            if txn_type is not None and category.applies_to is txn_type:
                self.category_combo.addItem(category.name, category.category_id)

    def _apply_initial(self) -> None:
        """用已有数据回填，用于"修改被驳回的记录"。"""
        if self._initial is None:
            return
        index = self.type_combo.findData(self._initial.txn_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self._populate_categories()
        category_index = self.category_combo.findData(self._initial.category_id)
        if category_index >= 0:
            self.category_combo.setCurrentIndex(category_index)
        self.amount_edit.setText(self._initial.amount)
        self.date_edit.setDate(QDate.fromString(self._initial.occurred_on, "yyyy-MM-dd"))
        self.note_edit.setPlainText(self._initial.note)

    # ------------------------------------------------------------------ 结果
    def value(self) -> RecordInput:
        """读取用户填写的内容。"""
        txn_type = combo_enum(self.type_combo, TxnType, TxnType.EXPENSE)
        return RecordInput(
            amount=self.amount_edit.text().strip(),
            txn_type=txn_type.value,
            category_id=str(self.category_combo.currentData() or ""),
            occurred_on=self.date_edit.date().toString("yyyy-MM-dd"),
            note=self.note_edit.toPlainText().strip(),
        )

    def accept(self) -> None:
        """保存前做最基本的非空检查。"""
        if not self.amount_edit.text().strip():
            self.amount_edit.setFocus()
            self.amount_edit.setPlaceholderText("请填写金额")
            return
        if self.category_combo.currentData() is None:
            self.category_combo.setFocus()
            return
        super().accept()

    @staticmethod
    def today_text() -> str:
        """今天的日期文本，供外部构造默认值。"""
        return date.today().isoformat()


__all__ = ["RecordDialog", "Qt"]
