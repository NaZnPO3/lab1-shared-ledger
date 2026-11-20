# pylint: disable=no-member,attribute-defined-outside-init,too-many-instance-attributes
"""主窗口：左侧账本列表，右侧按账本展示各功能页。"""

from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..errors import ValidationError
from ..models import Category, Ledger, Member
from ..money import parse_amount
from ..services.context import AppContext
from .helpers import FAILED, guard, show_error
from .logs_tab import LogsTab
from .members_tab import MembersTab
from .records_tab import RecordsTab
from .review_tab import ReviewTab
from .settlement_tab import SettlementTab
from .stats_tab import StatsTab


class NewLedgerDialog(QDialog):
    """新建账本：名称 + 可选金额上限。"""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建账本")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如 家庭账本（允许重名）")
        self.limit_edit = QLineEdit()
        self.limit_edit.setPlaceholderText("留空表示使用默认上限 1000000000")
        form.addRow("账本名称", self.name_edit)
        form.addRow("金额上限（元）", self.limit_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def name(self) -> str:
        """返回账本名称。"""
        return self.name_edit.text().strip()

    def limit(self) -> str:
        """返回金额上限文本，空串表示使用默认值。"""
        return self.limit_edit.text().strip()


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.ctx = context
        self.user = context.current_user
        self.ledger: Ledger | None = None
        self.member: Member | None = None
        self.members: list[Member] = []
        self.categories: list[Category] = []
        self.logout_requested = False
        self._build()
        self.reload_ledgers()

    # ------------------------------------------------------------------ 布局
    def _build(self) -> None:
        self.setWindowTitle("多人共享记账")
        self.resize(1200, 760)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_workspace())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 960])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage(f"数据库：{self.ctx.db_location}")
        self._build_toolbar()

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("主工具栏")
        toolbar.setMovable(False)

        new_ledger = QPushButton("＋ 新建账本")
        new_ledger.setObjectName("primary")
        new_ledger.clicked.connect(self._on_new_ledger)
        toolbar.addWidget(new_ledger)

        toolbar.addSeparator()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_all)
        toolbar.addWidget(refresh)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(spacer)

        self.user_label = QLabel(self._user_text())
        self.user_label.setObjectName("hint")
        toolbar.addWidget(self.user_label)

        logout = QPushButton("退出登录")
        logout.clicked.connect(self._on_logout)
        toolbar.addWidget(logout)

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 6, 10)
        layout.setSpacing(8)

        title = QLabel("我的账本")
        title.setObjectName("hint")
        layout.addWidget(title)

        self.ledger_list = QListWidget()
        self.ledger_list.currentItemChanged.connect(self._on_ledger_selected)
        layout.addWidget(self.ledger_list, 1)
        return panel

    def _build_workspace(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 10, 10, 10)
        layout.setSpacing(8)

        self.ledger_title = QLabel("尚未选择账本")
        self.ledger_title.setObjectName("title")
        layout.addWidget(self.ledger_title)

        self.ledger_subtitle = QLabel("在左侧选择一个账本，或新建一个账本开始记账")
        self.ledger_subtitle.setObjectName("hint")
        layout.addWidget(self.ledger_subtitle)

        self.tabs = QTabWidget()
        self.records_tab = RecordsTab(self)
        self.review_tab = ReviewTab(self)
        self.stats_tab = StatsTab(self)
        self.settlement_tab = SettlementTab(self)
        self.members_tab = MembersTab(self)
        self.logs_tab = LogsTab(self)
        self.tabs.addTab(self.records_tab, "记录")
        self.tabs.addTab(self.review_tab, "审核")
        self.tabs.addTab(self.stats_tab, "统计")
        self.tabs.addTab(self.settlement_tab, "结算")
        self.tabs.addTab(self.members_tab, "成员")
        self.tabs.addTab(self.logs_tab, "日志")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)
        return page

    def _user_text(self) -> str:
        """工具栏上的当前用户描述。"""
        if self.user is None:
            return ""
        return f"当前用户：{self.user.display_name}"

    # ------------------------------------------------------------------ 账本
    def reload_ledgers(self) -> None:
        """重新加载账本列表。"""
        ledgers = guard(self, self.ctx.ledgers.list_ledgers, self.user.user_id)
        self.ledger_list.blockSignals(True)
        self.ledger_list.clear()
        if ledgers is not FAILED:
            for ledger in ledgers:
                item = QListWidgetItem(ledger.name)
                item.setData(Qt.ItemDataRole.UserRole, ledger.ledger_id)
                self.ledger_list.addItem(item)
        self.ledger_list.blockSignals(False)

        if self.ledger_list.count() == 0:
            self.ledger = None
            self.member = None
            self.ledger_title.setText("还没有账本")
            self.ledger_subtitle.setText("点击工具栏“新建账本”开始使用")
            self._set_tabs_enabled(False)
            return

        self.ledger_list.setCurrentRow(0)
        self._on_ledger_selected(self.ledger_list.item(0), None)

    def _on_ledger_selected(self, current: QListWidgetItem | None, _previous) -> None:
        """切换账本时加载成员、分类并刷新各页。"""
        if current is None:
            return
        ledger_id = current.data(Qt.ItemDataRole.UserRole)
        selected = guard(self, self._find_ledger, ledger_id)
        if selected is FAILED or selected is None:
            return
        self.ledger = selected
        self.member = guard(self, self.ctx.ledgers.get_member, ledger_id, self.user.user_id)
        if self.member is FAILED:
            self.member = None

        self.ledger_title.setText(selected.name)
        role_text = self.member.role.label if self.member else "非成员"
        self.ledger_subtitle.setText(
            f"成员角色：{role_text}　|　金额上限：{selected.amount_limit_text} 元"
        )
        self._set_tabs_enabled(True)
        self.refresh_all()

    def _find_ledger(self, ledger_id: str) -> Ledger | None:
        """在用户可见账本中按 ID 查找。"""
        for ledger in self.ctx.ledgers.list_ledgers(self.user.user_id):
            if ledger.ledger_id == ledger_id:
                return ledger
        return None

    def _set_tabs_enabled(self, enabled: bool) -> None:
        """没有账本时禁用所有功能页。"""
        for index in range(self.tabs.count()):
            self.tabs.setTabEnabled(index, enabled)

    # ------------------------------------------------------------------ 刷新
    def refresh_all(self) -> None:
        """刷新所有页面的数据。"""
        if self.ledger is None or self.user is None:
            return
        user_id = self.user.user_id
        ledger_id = self.ledger.ledger_id

        members = guard(self, self.ctx.ledgers.list_members, user_id, ledger_id)
        if members is not FAILED:
            self.members = members
        categories = guard(self, self.ctx.ledgers.list_categories, user_id, ledger_id)
        if categories is not FAILED:
            self.categories = categories

        self.records_tab.refresh_member_filter()
        self.records_tab.refresh()
        self.review_tab.refresh()
        self.stats_tab.refresh()
        self.settlement_tab.refresh()
        self.members_tab.refresh()
        if self.member is not None:
            self.logs_tab.refresh()

    def _on_tab_changed(self, index: int) -> None:
        """切换页签时刷新对应页面。"""
        widget = self.tabs.widget(index)
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()

    def notify(self, message: str) -> None:
        """在状态栏显示一条提示。"""
        self.statusBar().showMessage(message, 5000)

    def next_request_key(self, prefix: str = "req") -> str:
        """为一次提交生成幂等键（REQ-016）。"""
        return f"{prefix}-{uuid.uuid4().hex}"

    # ------------------------------------------------------------------ 动作
    def _on_new_ledger(self) -> None:
        dialog = NewLedgerDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        limit_cents = None
        if dialog.limit():
            try:
                limit_cents = parse_amount(dialog.limit())
            except ValidationError as exc:
                show_error(self, exc)
                return
        ledger = guard(
            self,
            self.ctx.ledgers.create_ledger,
            self.user.user_id,
            dialog.name(),
            limit_cents,
        )
        if ledger is FAILED:
            return
        self.notify(f"账本“{ledger.name}”已创建")
        self.reload_ledgers()

    def _on_logout(self) -> None:
        self.logout_requested = True
        self.ctx.logout()
        self.close()
