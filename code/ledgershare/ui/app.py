# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""应用入口。

启动流程：创建应用上下文（自动建库）→ 登录窗口 → 主窗口。
退出登录后回到登录窗口，只有真正关掉程序才释放数据库连接。
"""

from __future__ import annotations

import sys
from typing import Sequence

from PySide6.QtWidgets import QApplication, QDialog

from ..config import APP_NAME, APP_VERSION
from ..services.context import AppContext
from .login_window import LoginWindow
from .main_window import MainWindow
from .theme import apply_theme


def main(argv: Sequence[str] | None = None) -> int:
    """程序入口，返回进程退出码。"""
    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    apply_theme(application)

    context = AppContext()
    try:
        while True:
            login = LoginWindow(context)
            if login.exec() != QDialog.DialogCode.Accepted:
                break
            window = MainWindow(context)
            window.show()
            application.exec()
            if not window.logout_requested:
                break
    finally:
        context.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动运行入口
    raise SystemExit(main())
