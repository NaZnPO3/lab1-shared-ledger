# pylint: disable=wrong-import-position,import-outside-toplevel
"""生成界面截图，用于实验报告展示。

用法::

    python tools/capture_ui.py

脚本会在 ``code/.demo`` 下重建一个演示数据库，塞入一组有代表性的数据，
然后把登录窗口和主窗口的各个页签渲染成 PNG，输出到仓库的 ``docs/screenshots``。
全程使用 Qt 的 offscreen 平台，不需要真实显示器。
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# offscreen 平台默认不带字体，指定系统字体目录才能渲染中文
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtWidgets import QApplication  # noqa: E402 - 需先设置平台插件

from ledgershare.domain.validation import RecordInput  # noqa: E402
from ledgershare.enums import Role, TxnType  # noqa: E402
from ledgershare.services.context import AppContext  # noqa: E402
from ledgershare.ui.login_window import LoginWindow  # noqa: E402
from ledgershare.ui.main_window import MainWindow  # noqa: E402
from ledgershare.ui.theme import apply_theme  # noqa: E402

OUTPUT_DIR = CODE_DIR.parent / "docs" / "screenshots"
DEMO_DB = CODE_DIR / ".demo" / "ledger.db"


def seed(context: AppContext) -> dict[str, str]:
    """写入演示数据，返回关键 ID。"""
    users = {
        "owner": context.auth.register("zhangwei", "secret123", "张伟"),
        "admin": context.auth.register("lina", "secret123", "李娜"),
        "member": context.auth.register("wangqiang", "secret123", "王强"),
        "readonly": context.auth.register("zhaomin", "secret123", "赵敏"),
    }
    ledger = context.ledgers.create_ledger(users["owner"].user_id, "家庭账本")
    context.ledgers.invite_member(
        users["owner"].user_id, ledger.ledger_id, "lina", Role.ADMIN
    )
    context.ledgers.invite_member(
        users["owner"].user_id, ledger.ledger_id, "wangqiang", Role.MEMBER
    )
    context.ledgers.invite_member(
        users["owner"].user_id, ledger.ledger_id, "zhaomin", Role.READONLY
    )

    categories = {
        category.name: category.category_id
        for category in context.ledgers.list_categories(
            users["owner"].user_id, ledger.ledger_id
        )
    }

    def add(user: str, amount: str, category: str, note: str, txn: TxnType = TxnType.EXPENSE):
        payload = RecordInput(
            amount=amount,
            txn_type=txn.value,
            category_id=categories[category],
            occurred_on=_today(),
            note=note,
        )
        return context.records.create_record(
            users[user].user_id, ledger.ledger_id, payload
        )

    lunch = add("member", "128.50", "餐饮", "周末聚餐")
    taxi = add("admin", "45.00", "交通", "打车回家")
    shopping = add("member", "399.00", "购物", "换季衣物")
    salary = add("admin", "12000.00", "工资", "十月工资", txn=TxnType.INCOME)
    rent = add("owner", "3000.00", "居住", "房租")

    for record in (lunch, taxi, shopping, salary, rent):
        context.review.approve(users["admin"].user_id, record.record_id)

    rejected = add("member", "260.00", "娱乐", "游戏充值（待补充票据）")
    context.review.reject(users["admin"].user_id, rejected.record_id, "请补充发票")

    context.settlements.settle(users["admin"].user_id, ledger.ledger_id)

    add("member", "68.00", "餐饮", "第二周期：早餐")
    second = add("admin", "1500.00", "购物", "第二周期：换电脑")
    context.review.approve(users["owner"].user_id, second.record_id)

    return {"ledger_id": ledger.ledger_id, "owner": users["owner"].user_id}


def _today() -> str:
    """返回今天的日期文本。"""
    return date.today().isoformat()


def capture(widget, name: str) -> None:
    """把控件渲染成 PNG。"""
    widget.grab().save(str(OUTPUT_DIR / f"{name}.png"))
    print(f"saved {name}.png")


def main() -> int:
    """重建演示库并输出截图。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if DEMO_DB.exists():
        DEMO_DB.unlink()

    application = QApplication(sys.argv)
    apply_theme(application)

    context = AppContext(DEMO_DB)
    try:
        ids = seed(context)
        context.login("lina", "secret123")

        login = LoginWindow(AppContext(DEMO_DB))
        login.show()
        application.processEvents()
        capture(login, "01-登录")
        login.close()

        window = MainWindow(context)
        window.resize(1280, 800)
        window.show()
        application.processEvents()

        for index, name in enumerate(
            ("02-记录", "03-审核", "04-统计", "05-结算", "06-成员", "07-日志")
        ):
            window.tabs.setCurrentIndex(index)
            application.processEvents()
            if name == "05-结算":
                window.settlement_tab.preview_current()
                application.processEvents()
            capture(window, name)

        window.close()
        _ = ids
    finally:
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
