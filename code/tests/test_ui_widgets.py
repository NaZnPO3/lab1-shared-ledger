# pylint: disable=redefined-outer-name
"""界面控件的回归测试（Qt offscreen 平台）。

覆盖两个曾经出现过的真实缺陷：

1. 记账对话框的"分类"下拉框是空的——因为 Qt 把 ``str`` 子类枚举还原成普通字符串，
   ``category.applies_to is txn_type`` 恒为假；
2. 筛选下拉框选中后抛 ``AttributeError: 'str' object has no attribute 'value'``。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from ledgershare.enums import TxnType
from ledgershare.ui.helpers import combo_enum
from ledgershare.ui.record_dialog import RecordDialog


@pytest.fixture(scope="session")
def qapp():
    """整个测试会话共用一个 QApplication。"""
    application = QApplication.instance() or QApplication([])
    yield application


# 本模块所有用例都需要 QApplication 存在，但多数并不直接使用该对象
pytestmark = pytest.mark.usefixtures("qapp")


def _items(combo: QComboBox) -> list[str]:
    """读取下拉框全部条目文本。"""
    return [combo.itemText(index) for index in range(combo.count())]


def test_combo_enum_rebuilds_enum_from_qstring() -> None:
    """Qt 的 userData 会丢掉枚举类型，读取时必须能还原。"""
    combo = QComboBox()
    combo.addItem("支出", TxnType.EXPENSE)  # noqa: F841 - 仅用于验证转换

    assert combo.currentData() == "expense"
    assert not isinstance(combo.currentData(), TxnType)
    assert combo_enum(combo, TxnType) is TxnType.EXPENSE


def test_combo_enum_handles_empty_and_unknown() -> None:
    """空选项与非法值都返回默认值，不抛异常。"""
    combo = QComboBox()
    combo.addItem("全部", None)
    assert combo_enum(combo, TxnType) is None
    assert combo_enum(combo, TxnType, TxnType.INCOME) is TxnType.INCOME


def test_record_dialog_fills_expense_categories(scenario) -> None:
    """新增记录时，支出分类必须可选（否则无法记账）。"""
    dialog = RecordDialog(None, scenario.categories())
    try:
        names = _items(dialog.category_combo)
        assert "餐饮" in names
        assert "工资" not in names
        assert dialog.value().txn_type == TxnType.EXPENSE.value
    finally:
        dialog.deleteLater()


def test_record_dialog_switches_to_income_categories(scenario) -> None:
    """切换收支类型后分类列表同步更新。"""
    dialog = RecordDialog(None, scenario.categories())
    try:
        index = dialog.type_combo.findData(TxnType.INCOME.value)
        dialog.type_combo.setCurrentIndex(index)

        names = _items(dialog.category_combo)
        assert "工资" in names
        assert "餐饮" not in names
        assert dialog.value().txn_type == TxnType.INCOME.value
    finally:
        dialog.deleteLater()


def test_record_dialog_value_can_be_saved(scenario) -> None:
    """对话框产出的数据能直接被服务层接受（端到端串起界面与业务）。"""
    dialog = RecordDialog(None, scenario.categories())
    try:
        dialog.amount_edit.setText("36.50")
        dialog.note_edit.setPlainText("晚饭")
        payload = dialog.value()
    finally:
        dialog.deleteLater()

    record = scenario.app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload
    )
    assert record.amount_cents == 3_650
    assert record.txn_type is TxnType.EXPENSE
