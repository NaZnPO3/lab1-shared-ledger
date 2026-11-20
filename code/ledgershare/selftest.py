"""打包自检：不打开界面，跑一遍"注册 → 登录 → 建账本 → 记账 → 审核 → 结算"。

打包成 exe 后最常见的问题是"某个依赖没被收进去"，而这类问题只有在运行时才暴露、
在 ``--windowed`` 模式下又看不到报错。``LedgerShare.exe --selftest`` 可以无人值守地
验证整条链路，并把结果写进日志文件（同时作为退出码返回）。
"""

from __future__ import annotations

import tempfile
import traceback
from datetime import date
from pathlib import Path

from .config import default_data_dir
from .domain.validation import RecordInput
from .enums import TxnType
from .money import format_cents
from .services.context import AppContext


def default_log_path() -> Path:
    """自检结果的默认日志位置。"""
    return default_data_dir() / "selftest.log"


def run(log_path: Path | None = None) -> int:
    """执行自检，成功返回 0，失败返回 1。"""
    target = Path(log_path) if log_path else default_log_path()
    lines: list[str] = []
    ok = True
    workdir = Path(tempfile.mkdtemp(prefix="ledgershare-selftest-"))
    db_path = workdir / "selftest.db"

    try:
        context = AppContext(db_path)
        try:
            user = context.auth.register("selftest_user", "secret123", "自检")
            lines.append(f"[ok] 注册用户 {user.username}")

            logged = context.auth.login("selftest_user", "secret123")
            assert logged.user_id == user.user_id
            lines.append("[ok] 登录成功（PBKDF2 校验通过）")

            ledger = context.ledgers.create_ledger(user.user_id, "自检账本")
            lines.append(f"[ok] 创建账本 {ledger.ledger_id[:8]}")

            categories = context.ledgers.list_categories(user.user_id, ledger.ledger_id)
            category = next(
                item for item in categories if item.applies_to is TxnType.EXPENSE
            )
            record = context.records.create_record(
                user.user_id,
                ledger.ledger_id,
                RecordInput(
                    amount="88.80",
                    txn_type=TxnType.EXPENSE.value,
                    category_id=category.category_id,
                    occurred_on=date.today().isoformat(),
                    note="自检记录",
                ),
            )
            lines.append(f"[ok] 记账 {format_cents(record.amount_cents)} 元")

            context.review.approve(user.user_id, record.record_id)
            lines.append("[ok] 审核通过")

            summary = context.settlements.settle(user.user_id, ledger.ledger_id)
            assert summary.total_expense_cents == 8_880
            lines.append(f"[ok] 结算完成，支出合计 {format_cents(summary.total_expense_cents)}")
            lines.append(f"[ok] 数据库位置 {db_path}")
        finally:
            context.close()
    except Exception:  # noqa: BLE001  pylint: disable=broad-exception-caught
        ok = False
        lines.append("[failed] 自检过程中出现异常：")
        lines.append(traceback.format_exc())

    text = "\n".join(lines)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass
    print(text)
    return 0 if ok else 1
