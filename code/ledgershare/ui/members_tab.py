# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""成员页：成员列表、邀请、角色调整、退出与账本设置。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..enums import Role
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

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

COLUMNS = ("昵称", "账号", "角色", "状态", "加入时间")


class InviteDialog(QDialog):
    """邀请成员：填账号并选择角色。"""

    def __init__(self, parent: QWidget | None, roles: list[Role]) -> None:
        super().__init__(parent)
        self.setWindowTitle("邀请成员")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("对方注册时使用的账号")
        self.role_combo = QComboBox()
        for role in roles:
            add_combo_item(self.role_combo, role.label, role)
        form.addRow("账号", self.username_edit)
        form.addRow("角色", self.role_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("邀请")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def username(self) -> str:
        """返回填写的账号。"""
        return self.username_edit.text().strip()

    def role(self) -> Role:
        """返回选择的角色。"""
        return self.role_combo.currentData()


class MembersTab(QWidget):
    """账本成员管理。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window
        self._members: dict[str, object] = {}
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        members_group = QGroupBox("成员")
        members_layout = QVBoxLayout(members_group)
        self.table = make_table(COLUMNS, stretch_column=0)
        self.table.itemSelectionChanged.connect(self._update_actions)
        members_layout.addWidget(self.table)

        actions = QHBoxLayout()
        self.invite_button = QPushButton("邀请成员")
        self.invite_button.clicked.connect(self._on_invite)
        self.role_button = QPushButton("调整角色")
        self.role_button.clicked.connect(self._on_change_role)
        self.leave_button = QPushButton("退出账本")
        self.leave_button.setObjectName("danger")
        self.leave_button.clicked.connect(self._on_leave)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.invite_button)
        actions.addWidget(self.role_button)
        actions.addWidget(self.leave_button)
        actions.addStretch(1)
        actions.addWidget(refresh_button)
        members_layout.addLayout(actions)
        layout.addWidget(members_group, 1)

        settings_group = QGroupBox("账本设置")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.addWidget(QLabel("金额上限（元）"))
        self.limit_edit = QLineEdit()
        self.limit_edit.setPlaceholderText("默认 1000000000")
        self.limit_edit.setFixedWidth(200)
        settings_layout.addWidget(self.limit_edit)
        self.save_limit_button = QPushButton("保存上限")
        self.save_limit_button.clicked.connect(self._on_save_limit)
        settings_layout.addWidget(self.save_limit_button)
        settings_layout.addStretch(1)
        self.limit_hint = QLabel("")
        self.limit_hint.setObjectName("hint")
        settings_layout.addWidget(self.limit_hint)
        layout.addWidget(settings_group)

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """刷新成员列表与设置。"""
        window = self.window
        if window.ledger is None or window.user is None:
            return
        members = guard(
            window, window.ctx.ledgers.list_members, window.user.user_id, window.ledger.ledger_id
        )
        if members is FAILED:
            return
        self._members = {member.member_id: member for member in members}
        fill_table(
            self.table,
            [
                (
                    member.display,
                    member.username,
                    member.role.label,
                    member.status.label,
                    member.joined_at.strftime("%Y-%m-%d %H:%M"),
                )
                for member in members
            ],
            [member.member_id for member in members],
        )
        self.limit_hint.setText(
            f"当前上限 {format_cents(window.ledger.amount_limit_cents)} 元"
        )
        self.limit_edit.setPlaceholderText(format_cents(window.ledger.amount_limit_cents))
        self._update_actions()

    def _update_actions(self) -> None:
        """按当前角色与选中成员决定按钮可用性。"""
        member = self.window.member
        is_admin = bool(member and member.role in (Role.OWNER, Role.ADMIN))
        self.invite_button.setEnabled(is_admin)
        self.role_button.setEnabled(is_admin and selected_id(self.table) is not None)
        self.leave_button.setEnabled(bool(member and member.role is not Role.OWNER))
        self.save_limit_button.setEnabled(is_admin)

    # ------------------------------------------------------------------ 动作
    def _on_invite(self) -> None:
        window = self.window
        roles = [Role.MEMBER, Role.READONLY]
        if window.member and window.member.role is Role.OWNER:
            roles.insert(0, Role.ADMIN)
        dialog = InviteDialog(self, roles)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        member = guard(
            window,
            window.ctx.ledgers.invite_member,
            window.user.user_id,
            window.ledger.ledger_id,
            dialog.username(),
            dialog.role(),
        )
        if member is not FAILED:
            window.notify(f"已邀请 {member.display} 加入账本")
            window.refresh_all()

    def _on_change_role(self) -> None:
        window = self.window
        member_id = selected_id(self.table)
        target = self._members.get(member_id) if member_id else None
        if target is None:
            return
        roles = [Role.MEMBER, Role.READONLY]
        if window.member and window.member.role is Role.OWNER:
            roles.append(Role.ADMIN)
        dialog = InviteDialog(self, roles)
        dialog.setWindowTitle("调整角色")
        dialog.username_edit.setText(target.username)
        dialog.username_edit.setEnabled(False)
        index = dialog.role_combo.findData(target.role)
        if index >= 0:
            dialog.role_combo.setCurrentIndex(index)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = guard(
            window,
            window.ctx.ledgers.change_member_role,
            window.user.user_id,
            window.ledger.ledger_id,
            member_id,
            dialog.role(),
        )
        if updated is not FAILED:
            window.notify(f"{updated.display} 的角色已调整为 {updated.role.label}")
            window.refresh_all()

    def _on_leave(self) -> None:
        window = self.window
        if not confirm(self, "确定退出该账本吗？退出后不能继续记账，历史记录会保留。"):
            return
        result = guard(
            window,
            window.ctx.ledgers.leave_ledger,
            window.user.user_id,
            window.ledger.ledger_id,
        )
        if result is not FAILED:
            window.notify("已退出该账本")
            window.reload_ledgers()

    def _on_save_limit(self) -> None:
        window = self.window
        text = self.limit_edit.text().strip()
        if not text:
            return
        ledger = guard(
            window,
            window.ctx.ledgers.set_amount_limit,
            window.user.user_id,
            window.ledger.ledger_id,
            text,
        )
        if ledger is not FAILED:
            window.notify(f"金额上限已调整为 {ledger.amount_limit_text} 元")
            window.refresh_all()
