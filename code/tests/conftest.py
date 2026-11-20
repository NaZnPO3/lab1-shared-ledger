# pylint: disable=redefined-outer-name
"""pytest 共享夹具：临时内存库 + 一个预置好的四人账本。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Callable

import pytest

from ledgershare.domain.validation import RecordInput
from ledgershare.enums import Role, TxnType
from ledgershare.models import Category, Ledger, TransactionRecord, User
from ledgershare.services.context import AppContext

# 界面用例使用无显示器平台，必须在任何 Qt 模块被导入之前设置。
# 这里导入的业务模块都不依赖 Qt，因此放在其后不影响生效。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")


@pytest.fixture()
def app(tmp_path) -> AppContext:
    """每个测试独立一个数据库文件（与正式运行一致，便于并发测试）。"""
    context = AppContext(tmp_path / "ledger.db")
    try:
        yield context
    finally:
        context.close()


@dataclass
class Scenario:
    """一个已建好、成员齐备的账本。"""

    app: AppContext
    ledger: Ledger
    users: dict[str, User]

    def uid(self, name: str) -> str:
        """取某个角色用户的 ID。"""
        return self.users[name].user_id

    def category_id(self, name: str) -> str:
        """按分类名取分类 ID。"""
        for category in self.categories():
            if category.name == name:
                return category.category_id
        raise AssertionError(f"分类 {name} 不存在")

    def categories(self) -> list[Category]:
        """列出账本分类。"""
        return self.app.ledgers.list_categories(self.uid("owner"), self.ledger.ledger_id)

    @property
    def ledger_id(self) -> str:
        """账本 ID 的快捷方式。"""
        return self.ledger.ledger_id


@pytest.fixture()
def scenario(app: AppContext) -> Scenario:
    """owner / admin / member / readonly 四人共用一个账本。"""
    users = {
        "owner": app.auth.register("owner", "secret123", "创建者"),
        "admin": app.auth.register("admin", "secret123", "管理员"),
        "member": app.auth.register("member", "secret123", "成员甲"),
        "readonly": app.auth.register("readonly", "secret123", "只读乙"),
    }
    ledger = app.ledgers.create_ledger(users["owner"].user_id, "家庭账本")
    app.ledgers.invite_member(users["owner"].user_id, ledger.ledger_id, "admin", Role.ADMIN)
    app.ledgers.invite_member(users["owner"].user_id, ledger.ledger_id, "member", Role.MEMBER)
    app.ledgers.invite_member(
        users["owner"].user_id, ledger.ledger_id, "readonly", Role.READONLY
    )
    return Scenario(app=app, ledger=ledger, users=users)


@pytest.fixture()
def payload(scenario: Scenario) -> Callable[..., RecordInput]:
    """返回构造记录输入的函数。"""

    def build(
        *,
        amount: str = "100",
        txn_type: TxnType = TxnType.EXPENSE,
        category: str = "餐饮",
        occurred_on: str | None = None,
        note: str = "",
    ) -> RecordInput:
        return RecordInput(
            amount=amount,
            txn_type=txn_type.value,
            category_id=scenario.category_id(category),
            occurred_on=occurred_on or date.today().isoformat(),
            note=note,
        )

    return build


@pytest.fixture()
def make_record(
    scenario: Scenario, payload: Callable[..., RecordInput]
) -> Callable[..., TransactionRecord]:
    """返回"以某个用户身份新增记录"的函数。"""

    def create(user: str, idem_key: str | None = None, **kwargs) -> TransactionRecord:
        return scenario.app.records.create_record(
            scenario.uid(user),
            scenario.ledger_id,
            payload(**kwargs),
            idem_key=idem_key,
        )

    return create
