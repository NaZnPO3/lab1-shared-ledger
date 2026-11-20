# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""登录 / 注册窗口。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..services.context import AppContext
from .helpers import FAILED, guard, show_info


class LoginWindow(QDialog):
    """启动后首先出现的窗口，登录成功后进入主窗口。"""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("多人共享记账 · 登录")
        self.setMinimumWidth(430)
        self._build()

    # ------------------------------------------------------------------ 布局
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("多人共享记账")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("轻量级 Windows 桌面版 · 单机多账号共享账本")
        subtitle.setObjectName("hint")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.addTab(self._build_login_tab(), "登录")
        tabs.addTab(self._build_register_tab(), "注册")
        layout.addWidget(tabs)

        footer = QLabel(f"数据文件：{self.context.db_location}")
        footer.setObjectName("hint")
        footer.setWordWrap(True)
        layout.addWidget(footer)

    def _build_login_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("账号")
        self.login_password = QLineEdit()
        self.login_password.setPlaceholderText("密码")
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("账号", self.login_username)
        layout.addRow("密码", self.login_password)

        button = QPushButton("登 录")
        button.setObjectName("primary")
        button.clicked.connect(self._do_login)
        self.login_password.returnPressed.connect(self._do_login)
        layout.addRow("", button)
        return page

    def _build_register_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.register_username = QLineEdit()
        self.register_username.setPlaceholderText("3~20 位字母、数字或下划线")
        self.register_nickname = QLineEdit()
        self.register_nickname.setPlaceholderText("留空则使用账号")
        self.register_password = QLineEdit()
        self.register_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.register_confirm = QLineEdit()
        self.register_confirm.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("账号", self.register_username)
        layout.addRow("昵称", self.register_nickname)
        layout.addRow("密码", self.register_password)
        layout.addRow("确认密码", self.register_confirm)

        row = QHBoxLayout()
        button = QPushButton("注册并登录")
        button.setObjectName("primary")
        button.clicked.connect(self._do_register)
        row.addWidget(button)
        layout.addRow("", row)
        return page

    # ------------------------------------------------------------------ 动作
    def _do_login(self) -> None:
        user = guard(
            self,
            self.context.login,
            self.login_username.text(),
            self.login_password.text(),
        )
        if user is not FAILED:
            self.accept()

    def _do_register(self) -> None:
        if self.register_password.text() != self.register_confirm.text():
            show_info(self, "两次输入的密码不一致")
            return
        user = guard(
            self,
            self.context.auth.register,
            self.register_username.text(),
            self.register_password.text(),
            self.register_nickname.text(),
        )
        if user is FAILED:
            return
        if guard(self, self.context.login, user.username, self.register_password.text()) is FAILED:
            return
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 事件命名
        """回车直接登录。"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._do_login()
        super().keyPressEvent(event)
