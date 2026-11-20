# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""界面主题样式。

只使用 Qt 内置的样式表能力，不依赖任何图片资源，保证打包成 exe 后观感一致。
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

PRIMARY = "#2f6fed"
PRIMARY_DARK = "#1f56c9"
DANGER = "#d93f3f"
BORDER = "#dfe3ea"
TEXT = "#1f2430"
MUTED = "#6b7280"
BACKGROUND = "#f5f7fb"

APP_QSS = f"""
QWidget {{
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {BACKGROUND};
}}
QPushButton {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    border-color: {PRIMARY};
    color: {PRIMARY};
}}
QPushButton:disabled {{
    color: #b6bcc8;
    border-color: #e8ebf1;
}}
QPushButton#primary {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {PRIMARY_DARK};
}}
QPushButton#danger {{
    color: {DANGER};
    border-color: #f0c4c4;
}}
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 20px;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{
    border-color: {PRIMARY};
}}
QTableWidget {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: #eef1f6;
    selection-background-color: #e6efff;
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: #f0f3f9;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
    color: {MUTED};
}}
QListWidget {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background: #e6efff;
    color: {PRIMARY};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 18px;
    margin-right: 4px;
    border-radius: 6px;
    color: {MUTED};
}}
QTabBar::tab:selected {{
    background: #ffffff;
    color: {PRIMARY};
    font-weight: 600;
    border: 1px solid {BORDER};
    border-bottom-color: #ffffff;
}}
QGroupBox {{
    background: #ffffff;
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {MUTED};
}}
QLabel#hint {{
    color: {MUTED};
}}
QLabel#title {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel#amount {{
    font-size: 16px;
    font-weight: 700;
    color: {PRIMARY};
}}
"""


def apply_theme(application: QApplication) -> None:
    """把样式表应用到整个应用。"""
    application.setStyle("Fusion")
    application.setStyleSheet(APP_QSS)
