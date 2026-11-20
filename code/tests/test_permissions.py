"""权限矩阵与角色调整规则的单元测试（REQ-003）。"""

from __future__ import annotations

import pytest

from ledgershare.domain.permissions import (
    can_manage_role,
    check_invite_role,
    check_role_change,
    has_permission,
    permissions_for,
)
from ledgershare.enums import Permission, Role
from ledgershare.errors import PermissionDenied


def test_readonly_can_only_view() -> None:
    """只读成员不能新增、修改、撤回、审核、作废（REQ-020）。"""
    assert has_permission(Role.READONLY, Permission.VIEW_RECORDS)
    for permission in (
        Permission.CREATE_RECORD,
        Permission.WITHDRAW_OWN_RECORD,
        Permission.EDIT_OWN_RECORD,
        Permission.REVIEW_RECORD,
        Permission.VOID_RECORD,
        Permission.RUN_SETTLEMENT,
    ):
        assert not has_permission(Role.READONLY, permission)


def test_member_can_record_but_not_review() -> None:
    """普通成员可以记账，但不能审核。"""
    assert has_permission(Role.MEMBER, Permission.CREATE_RECORD)
    assert has_permission(Role.MEMBER, Permission.WITHDRAW_OWN_RECORD)
    assert not has_permission(Role.MEMBER, Permission.REVIEW_RECORD)


def test_admin_permissions() -> None:
    """管理员负责审核、作废、结算与邀请。"""
    assert has_permission(Role.ADMIN, Permission.REVIEW_RECORD)
    assert has_permission(Role.ADMIN, Permission.VOID_RECORD)
    assert has_permission(Role.ADMIN, Permission.RUN_SETTLEMENT)
    assert has_permission(Role.ADMIN, Permission.INVITE_MEMBER)


def test_owner_has_every_permission() -> None:
    """创建者拥有全部权限。"""
    assert permissions_for(Role.OWNER) == frozenset(Permission)


def test_can_manage_role_rules() -> None:
    """管理员只能调整普通成员和只读成员，创建者可以调整管理员。"""
    assert can_manage_role(Role.ADMIN, Role.MEMBER)
    assert can_manage_role(Role.ADMIN, Role.READONLY)
    assert not can_manage_role(Role.ADMIN, Role.ADMIN)
    assert not can_manage_role(Role.ADMIN, Role.OWNER)
    assert can_manage_role(Role.OWNER, Role.ADMIN)
    assert not can_manage_role(Role.OWNER, Role.OWNER)
    assert not can_manage_role(Role.MEMBER, Role.READONLY)


def test_check_role_change_rejects_owner_and_admin_promotion() -> None:
    """创建者角色不可变更，管理员不能把成员提为管理员。"""
    with pytest.raises(PermissionDenied):
        check_role_change(Role.OWNER, Role.OWNER, Role.MEMBER)
    with pytest.raises(PermissionDenied):
        check_role_change(Role.ADMIN, Role.MEMBER, Role.ADMIN)
    check_role_change(Role.OWNER, Role.MEMBER, Role.ADMIN)
    check_role_change(Role.OWNER, Role.ADMIN, Role.MEMBER)


def test_check_invite_role_limits() -> None:
    """管理员不能邀请管理员，也不能通过邀请产生第二个创建者。"""
    check_invite_role(Role.ADMIN, Role.MEMBER)
    with pytest.raises(PermissionDenied):
        check_invite_role(Role.ADMIN, Role.ADMIN)
    with pytest.raises(PermissionDenied):
        check_invite_role(Role.OWNER, Role.OWNER)
