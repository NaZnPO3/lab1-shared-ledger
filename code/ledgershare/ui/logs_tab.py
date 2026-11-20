# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""操作日志页：只追加的审计记录，管理员可查。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..enums import LogAction, LogResult
from .helpers import FAILED, fill_table, guard, make_table

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

COLUMNS = ("时间", "操作人", "操作", "结果", "详情")


class LogsTab(QWidget):
    """账本操作日志。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        self.hint = QLabel("日志只追加，不随业务操作回滚")
        self.hint.setObjectName("hint")
        actions.addWidget(refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.hint)
        layout.addLayout(actions)

        self.table = make_table(COLUMNS, stretch_column=4)
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        """加载最近 200 条日志。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        entries = guard(
            window,
            window.ctx.logs.list_for_ledger,
            window.user.user_id,
            window.ledger.ledger_id,
        )
        if entries is FAILED:
            fill_table(self.table, [])
            return
        names = {member.member_id: member.display for member in window.members}
        fill_table(
            self.table,
            [
                (
                    entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    names.get(entry.actor_member_id or "", entry.actor_user_id[:8]),
                    _action_label(entry.action),
                    _result_label(entry.result),
                    entry.detail,
                )
                for entry in entries
            ],
            [entry.log_id for entry in entries],
        )
        self.hint.setText(f"最近 {len(entries)} 条日志（最多显示 200 条）")


def _action_label(value: str) -> str:
    """把日志里的操作代码转成中文。"""
    try:
        return LogAction(value).label
    except ValueError:
        return value


def _result_label(value: str) -> str:
    """把日志里的结果代码转成中文。"""
    try:
        return LogResult(value).label
    except ValueError:
        return value
