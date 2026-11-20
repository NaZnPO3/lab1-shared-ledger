# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""界面通用工具：错误提示、表格构建与选择行读取。"""

from __future__ import annotations

import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
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

from ..config import default_data_dir
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


def error_log_path() -> Path:
    """返回错误日志文件位置。"""
    return default_data_dir() / "error.log"


def report_unexpected(exc: BaseException, tb: object | None = None) -> Path:
    """把未预期异常的完整栈写入日志文件，返回日志路径。

    打包成窗口程序后没有控制台，异常栈只能落到文件里，否则用户和开发者都无从查起。
    """
    path = error_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    detail = "".join(traceback.format_exception(type(exc), exc, tb)) if tb else "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {stamp} =====\n{detail}")
    return path


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
    """执行一次业务调用，失败时弹窗并返回 :data:`FAILED`。

    业务异常按提示文案展示；未预期的异常（打包缺库、编码问题等）也会弹窗并
    写入错误日志，绝不让按钮"点了没反应"——窗口模式下 stderr 是不可见的。
    """
    try:
        return func(*args, **kwargs)
    except LedgerError as exc:
        show_error(parent, exc)
        return FAILED
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-exception-caught
        report_unexpected(exc)
        QMessageBox.critical(
            parent,
            "程序异常",
            f"发生了未预期的错误：\n{type(exc).__name__}: {exc}\n\n"
            f"详细信息已写入：\n{error_log_path()}",
        )
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
