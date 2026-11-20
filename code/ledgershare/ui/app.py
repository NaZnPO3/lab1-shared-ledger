# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""应用入口。

启动流程：创建应用上下文（自动建库）→ 登录窗口 → 主窗口。
退出登录后回到登录窗口，只有真正关掉程序才释放数据库连接。
"""

from __future__ import annotations

import sys
import traceback
from typing import Sequence

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ..config import APP_NAME, APP_VERSION
from ..services.context import AppContext
from .helpers import error_log_path, report_unexpected
from .login_window import LoginWindow
from .main_window import MainWindow
from .theme import apply_theme

#: 防止异常处理本身再次抛异常导致无限递归。
_REPORTING = False


def install_exception_hook() -> None:
    """把未捕获异常写进日志并弹窗。

    打包成 ``--windowed`` 的 exe 后没有控制台，默认的 ``sys.excepthook`` 只是把
    栈打到 stderr，用户看到的就是"按钮点了没反应"。这里改为落盘 + 弹窗。
    """

    def hook(exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001 - 固定签名
        global _REPORTING  # pylint: disable=global-statement
        if _REPORTING:
            return
        _REPORTING = True
        try:
            report_unexpected(exc_value, exc_tb)
            sys.stderr.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            QMessageBox.critical(
                None,
                "程序异常",
                f"发生了未预期的错误：\n{exc_type.__name__}: {exc_value}\n\n"
                f"详细信息已写入：\n{error_log_path()}",
            )
        finally:
            _REPORTING = False

    sys.excepthook = hook


def main(argv: Sequence[str] | None = None) -> int:
    """程序入口，返回进程退出码。"""
    application = QApplication(list(argv) if argv is not None else sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    apply_theme(application)
    install_exception_hook()

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
