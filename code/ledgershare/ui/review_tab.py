# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""审核中心：处理待审核记录、作废已审核记录。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..domain.permissions import has_permission
from ..enums import Permission, RecordStatus
from ..money import format_cents
from .helpers import FAILED, fill_table, guard, make_table, selected_id

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

COLUMNS = ("日期", "类型", "分类", "金额（元）", "记录人", "备注", "说明")


class ReviewTab(QWidget):
    """管理员审核与作废。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._pending: dict[str, object] = {}
        self._approved: dict[str, object] = {}
        self._build()

    # ------------------------------------------------------------------ 布局
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        pending_group = QGroupBox("待审核")
        pending_layout = QVBoxLayout(pending_group)
        self.pending_table = make_table(COLUMNS, stretch_column=5)
        self.pending_table.itemSelectionChanged.connect(self._update_actions)
        pending_layout.addWidget(self.pending_table)

        pending_actions = QHBoxLayout()
        self.approve_button = QPushButton("通过")
        self.approve_button.setObjectName("primary")
        self.approve_button.clicked.connect(self._on_approve)
        self.reject_button = QPushButton("驳回")
        self.reject_button.setObjectName("danger")
        self.reject_button.clicked.connect(self._on_reject)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        pending_actions.addWidget(self.approve_button)
        pending_actions.addWidget(self.reject_button)
        pending_actions.addStretch(1)
        pending_actions.addWidget(refresh_button)
        pending_layout.addLayout(pending_actions)
        layout.addWidget(pending_group, 3)

        approved_group = QGroupBox("已审核（可作废）")
        approved_layout = QVBoxLayout(approved_group)
        self.approved_table = make_table(COLUMNS, stretch_column=5)
        self.approved_table.itemSelectionChanged.connect(self._update_actions)
        approved_layout.addWidget(self.approved_table)

        approved_actions = QHBoxLayout()
        self.void_button = QPushButton("作废")
        self.void_button.setObjectName("danger")
        self.void_button.clicked.connect(self._on_void)
        self.hint = QLabel("作废只是把状态改为已作废，记录与日志均保留")
        self.hint.setObjectName("hint")
        approved_actions.addWidget(self.void_button)
        approved_actions.addStretch(1)
        approved_actions.addWidget(self.hint)
        approved_layout.addLayout(approved_actions)
        layout.addWidget(approved_group, 2)

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """加载待审核与已审核记录。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        service = window.ctx.records
        pending = guard(
            window,
            service.list_records,
            window.user.user_id,
            window.ledger.ledger_id,
            statuses=[RecordStatus.PENDING],
        )
        approved = guard(
            window,
            service.list_records,
            window.user.user_id,
            window.ledger.ledger_id,
            statuses=[RecordStatus.APPROVED],
        )
        if pending is FAILED or approved is FAILED:
            return

        self._pending = {view.record.record_id: view for view in pending}
        self._approved = {view.record.record_id: view for view in approved}
        fill_table(
            self.pending_table,
            [self._row(view) for view in pending],
            [view.record.record_id for view in pending],
        )
        fill_table(
            self.approved_table,
            [self._row(view) for view in approved],
            [view.record.record_id for view in approved],
        )
        self.hint.setText(
            f"待审核 {len(pending)} 条，已审核 {len(approved)} 条；作废只改状态，记录与日志均保留"
        )
        self._update_actions()

    @staticmethod
    def _row(view) -> tuple[str, ...]:
        """把记录视图转成表格行。"""
        note = "更正记录" if view.record.corrects_record_id else ""
        return (
            view.record.occurred_on.isoformat(),
            view.record.txn_type.label,
            view.category_name,
            format_cents(view.record.amount_cents),
            view.member_name,
            view.record.note,
            note,
        )

    def _update_actions(self) -> None:
        """只有管理员才能点通过、驳回、作废。"""
        member = self.window.member
        can_review = bool(
            member is not None
            and has_permission(member.role, Permission.REVIEW_RECORD)
        )
        self.approve_button.setEnabled(can_review)
        self.reject_button.setEnabled(can_review)
        self.void_button.setEnabled(can_review)

    # ------------------------------------------------------------------ 动作
    def _on_approve(self) -> None:
        record_id = selected_id(self.pending_table)
        if record_id is None:
            return
        result = guard(
            self.window,
            self.window.ctx.review.approve,
            self.window.user.user_id,
            record_id,
        )
        if result is not FAILED:
            self.window.notify("已审核通过")
            self.window.refresh_all()

    def _on_reject(self) -> None:
        record_id = selected_id(self.pending_table)
        if record_id is None:
            return
        reason, accepted = QInputDialog.getText(self, "驳回原因", "填写驳回原因（可留空）：")
        if not accepted:
            return
        result = guard(
            self.window,
            self.window.ctx.review.reject,
            self.window.user.user_id,
            record_id,
            reason,
        )
        if result is not FAILED:
            self.window.notify("已驳回，原记录人可修改后重新提交")
            self.window.refresh_all()

    def _on_void(self) -> None:
        record_id = selected_id(self.approved_table)
        if record_id is None:
            return
        reason, accepted = QInputDialog.getText(self, "作废原因", "填写作废原因（可留空）：")
        if not accepted:
            return
        result = guard(
            self.window,
            self.window.ctx.review.void,
            self.window.user.user_id,
            record_id,
            reason,
        )
        if result is not FAILED:
            self.window.notify("已作废该记录")
            self.window.refresh_all()
