"""全局配置常量。

账本金额上限、默认分类、密码散列参数等集中在此，避免散落在业务代码里。
"""

from __future__ import annotations

import os
from pathlib import Path

from .enums import TxnType

APP_NAME = "多人共享记账"
APP_VERSION = "1.0.0"

#: REQ-015 规定的默认金额上限：1e9 元，内部以分保存。
DEFAULT_AMOUNT_LIMIT_CENTS = 1_000_000_000 * 100

#: 密码散列迭代次数（PBKDF2-HMAC-SHA256）。
PASSWORD_ITERATIONS = 240_000
PASSWORD_MIN_LENGTH = 6

#: 默认数据库文件名与目录。
DEFAULT_DB_FILENAME = "ledger.db"

#: 账本创建时自动生成的分类，避免用户为空分类发愁。
DEFAULT_CATEGORIES: tuple[tuple[str, TxnType], ...] = (
    ("餐饮", TxnType.EXPENSE),
    ("交通", TxnType.EXPENSE),
    ("购物", TxnType.EXPENSE),
    ("居住", TxnType.EXPENSE),
    ("娱乐", TxnType.EXPENSE),
    ("其他支出", TxnType.EXPENSE),
    ("工资", TxnType.INCOME),
    ("奖金", TxnType.INCOME),
    ("其他收入", TxnType.INCOME),
)


def default_data_dir() -> Path:
    """返回默认数据目录（Windows 下为 ``%LOCALAPPDATA%\\LedgerShare``）。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    return root / "LedgerShare"


def default_db_path() -> Path:
    """返回默认数据库文件路径。"""
    override = os.environ.get("LEDGERSHARE_DB")
    if override:
        return Path(override)
    return default_data_dir() / DEFAULT_DB_FILENAME
