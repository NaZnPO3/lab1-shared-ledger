# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""界面通用工具：错误提示、表格构建与选择行读取。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..errors import LedgerError

#: 表示 ``guard`` 执行失败（区别于函数本来返回 None）。
FAILED = object()


def show_error(parent: QWidget | None, exc: Exception) -> None:
    """用对话框展示业务异常。"""
    text = exc.message if isinstance(exc, LedgerError) else str(exc)
    QMessageBox.warning(parent, "操作未完成", text)


def show_info(parent: QWidget | None, text: str) -> None:
    """展示普通提示。"""
    QMessageBox.information(parent, "提示", text)


def confirm(parent: QWidget | None, text: str) -> bool:
    """询问用户是否继续。"""
    answer = QMessageBox.question(
        parent,
        "确认",
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def guard(
    parent: QWidget | None, func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """执行一次业务调用，失败时弹窗并返回 :data:`FAILED`。"""
    try:
        return func(*args, **kwargs)
    except LedgerError as exc:
        show_error(parent, exc)
        return FAILED


def make_table(
    headers: Sequence[str],
    *,
    stretch_column: int | None = None,
) -> QTableWidget:
    """创建一个只读、整行选中的表格。"""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setHighlightSections(False)
    if stretch_column is not None:
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
    return table


def fill_table(
    table: QTableWidget,
    rows: Sequence[Sequence[str]],
    row_ids: Sequence[str] | None = None,
) -> None:
    """填充表格内容，并把业务 ID 挂到首列以便选中后取回。"""
    table.setRowCount(0)
    for index, values in enumerate(rows):
        table.insertRow(index)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            )
            table.setItem(index, column, item)
        if row_ids is not None and index < len(row_ids):
            first = table.item(index, 0)
            if first is not None:
                first.setData(Qt.ItemDataRole.UserRole, row_ids[index])


def selected_id(table: QTableWidget) -> str | None:
    """返回当前选中行的业务 ID。"""
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    value = item.data(Qt.ItemDataRole.UserRole)
    return str(value) if value else None


def add_combo_item(combo: QComboBox, label: str, value: Any) -> None:
    """向下拉框追加一项，值保存在 ``userData``。"""
    combo.addItem(label, value)


def combo_value(combo: QComboBox, default: Any = None) -> Any:
    """读取下拉框当前项的值。"""
    data = combo.currentData()
    return default if data is None else data


def combo_enum(
    combo: QComboBox, enum_cls: type[Enum], default: Any = None
) -> Any:
    """读取下拉框中的枚举值。

    Qt 会把 ``str`` 子类的枚举（本项目所有枚举都继承 ``str``）在存入 ``userData``
    时转成普通字符串，``currentData()`` 拿回来的不再是枚举实例。因此统一在读取处
    用枚举构造器还原，避免各处再出现 ``'str' object has no attribute 'value'``。

    Args:
        combo: 下拉框。
        enum_cls: 期望的枚举类型。
        default: 没有选中项或取值非法时返回的默认值。

    Returns:
        枚举实例或默认值。
    """
    data = combo.currentData()
    if data is None:
        return default
    if isinstance(data, enum_cls):
        return data
    try:
        return enum_cls(data)
    except ValueError:
        return default
