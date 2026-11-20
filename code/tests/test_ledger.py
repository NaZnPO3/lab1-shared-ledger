"""账本与成员服务测试（REQ-001、REQ-002、REQ-003、REQ-004、REQ-015）。"""

from __future__ import annotations

import pytest

from ledgershare.enums import MemberStatus, Role
from ledgershare.errors import (
    DuplicateError,
    NotFound,
    PermissionDenied,
    ValidationError,
)


def test_create_ledger_creates_owner_categories_and_period(scenario, app) -> None:
    """建账本时同时生成创建者成员、默认分类和第一个结算周期。"""
    members = app.ledgers.list_members(scenario.uid("owner"), scenario.ledger_id)
    owner = [member for member in members if member.role is Role.OWNER]
    assert len(owner) == 1
    assert owner[0].user_id == scenario.uid("owner")

    assert len(scenario.categories()) >= 5

    period = app.ledgers.current_period(scenario.uid("owner"), scenario.ledger_id)
    assert period.seq == 1
    assert period.is_open


def test_duplicate_ledger_names_are_allowed(app) -> None:
    """同名账本可以并存，用 ID 区分（REQ-001）。"""
    user = app.auth.register("solo", "secret123")
    first = app.ledgers.create_ledger(user.user_id, "旅行")
    second = app.ledgers.create_ledger(user.user_id, "旅行")
    assert first.ledger_id != second.ledger_id
    assert first.name == second.name == "旅行"


def test_invite_member_and_duplicate_invite(scenario, app) -> None:
    """重复邀请同一用户应被拒绝。"""
    with pytest.raises(DuplicateError):
        app.ledgers.invite_member(
            scenario.uid("owner"), scenario.ledger_id, "member", Role.MEMBER
        )


def test_invite_unknown_account(scenario, app) -> None:
    """邀请未注册账号时提示账号不存在。"""
    with pytest.raises(NotFound):
        app.ledgers.invite_member(
            scenario.uid("owner"), scenario.ledger_id, "ghost", Role.MEMBER
        )


def test_admin_cannot_invite_admin(scenario, app) -> None:
    """管理员邀请管理员越权，但可以邀请普通成员。"""
    app.auth.register("newbie", "secret123")
    with pytest.raises(PermissionDenied):
        app.ledgers.invite_member(
            scenario.uid("admin"), scenario.ledger_id, "newbie", Role.ADMIN
        )
    member = app.ledgers.invite_member(
        scenario.uid("admin"), scenario.ledger_id, "newbie", Role.MEMBER
    )
    assert member.role is Role.MEMBER


def test_member_cannot_invite(scenario, app) -> None:
    """普通成员没有邀请权限。"""
    app.auth.register("friend", "secret123")
    with pytest.raises(PermissionDenied):
        app.ledgers.invite_member(
            scenario.uid("member"), scenario.ledger_id, "friend", Role.MEMBER
        )


def test_change_role_permissions(scenario, app) -> None:
    """管理员不能调整管理员的角色，创建者可以。"""
    members = app.ledgers.list_members(scenario.uid("owner"), scenario.ledger_id)
    admin_member = next(member for member in members if member.role is Role.ADMIN)
    plain_member = next(member for member in members if member.role is Role.MEMBER)

    with pytest.raises(PermissionDenied):
        app.ledgers.change_member_role(
            scenario.uid("admin"), scenario.ledger_id, admin_member.member_id, Role.MEMBER
        )

    promoted = app.ledgers.change_member_role(
        scenario.uid("owner"), scenario.ledger_id, plain_member.member_id, Role.ADMIN
    )
    assert promoted.role is Role.ADMIN


def test_leave_ledger_requires_settlement(scenario, app, make_record) -> None:
    """当前周期有未结算记录时不能退出（REQ-004）。"""
    make_record("member", amount="10")
    with pytest.raises(ValidationError):
        app.ledgers.leave_ledger(scenario.uid("member"), scenario.ledger_id)


def test_leave_ledger_without_records(scenario, app, payload) -> None:
    """没有未结算记录时可以退出，退出后不能记账（REQ-004）。"""
    app.ledgers.leave_ledger(scenario.uid("member"), scenario.ledger_id)
    members = app.ledgers.list_members(scenario.uid("owner"), scenario.ledger_id)
    left = next(member for member in members if member.user_id == scenario.uid("member"))
    assert left.status is MemberStatus.LEFT

    with pytest.raises(PermissionDenied):
        app.records.create_record(
            scenario.uid("member"), scenario.ledger_id, payload()
        )


def test_owner_cannot_leave(scenario, app) -> None:
    """创建者不能退出，避免账本失去所有者。"""
    with pytest.raises(PermissionDenied):
        app.ledgers.leave_ledger(scenario.uid("owner"), scenario.ledger_id)


def test_amount_limit_can_be_updated(scenario, app) -> None:
    """管理员可以调整金额上限，普通成员不行（REQ-015）。"""
    ledger = app.ledgers.set_amount_limit(
        scenario.uid("admin"), scenario.ledger_id, "500"
    )
    assert ledger.amount_limit_cents == 50_000
    with pytest.raises(PermissionDenied):
        app.ledgers.set_amount_limit(scenario.uid("member"), scenario.ledger_id, "800")


def test_outsider_cannot_read_ledger(app, scenario) -> None:
    """非成员无法查看账本记录（REQ-020）。"""
    outsider = app.auth.register("outsider", "secret123")
    with pytest.raises(PermissionDenied):
        app.records.list_records(outsider.user_id, scenario.ledger_id)
