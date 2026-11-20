"""角色权限矩阵（REQ-003、REQ-020）。

权限判定的唯一入口在这里，服务层所有写操作都必须先经过 :func:`check_permission`，
这样"未授权操作不得改变业务数据"不会因为某个入口漏检而失效。
"""

from __future__ import annotations

from ..enums import Permission, Role
from ..errors import PermissionDenied

#: 只读成员仅能查看记录与统计。
_READONLY_PERMISSIONS = frozenset(
    {
        Permission.VIEW_RECORDS,
        Permission.VIEW_STATS,
    }
)

#: 普通成员可记录、撤回、修改和更正自己的记录，但不能审核。
_MEMBER_PERMISSIONS = _READONLY_PERMISSIONS | frozenset(
    {
        Permission.CREATE_RECORD,
        Permission.WITHDRAW_OWN_RECORD,
        Permission.EDIT_OWN_RECORD,
        Permission.CORRECT_OWN_RECORD,
    }
)

#: 管理员负责审核与结算，但同样只能改动自己提交的记录。
_ADMIN_PERMISSIONS = _MEMBER_PERMISSIONS | frozenset(
    {
        Permission.REVIEW_RECORD,
        Permission.VOID_RECORD,
        Permission.RUN_SETTLEMENT,
        Permission.INVITE_MEMBER,
        Permission.CHANGE_MEMBER_ROLE,
        Permission.EDIT_LEDGER,
        Permission.VIEW_LOGS,
    }
)

#: 创建者拥有账本内的全部权限。
_OWNER_PERMISSIONS = _ADMIN_PERMISSIONS | frozenset(Permission)

PERMISSION_MATRIX: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _OWNER_PERMISSIONS,
    Role.ADMIN: _ADMIN_PERMISSIONS,
    Role.MEMBER: _MEMBER_PERMISSIONS,
    Role.READONLY: _READONLY_PERMISSIONS,
}


def permissions_for(role: Role) -> frozenset[Permission]:
    """返回某个角色拥有的权限集合。"""
    return PERMISSION_MATRIX[role]


def has_permission(role: Role, permission: Permission) -> bool:
    """判断角色是否拥有指定权限。"""
    return permission in PERMISSION_MATRIX[role]


def check_permission(role: Role, permission: Permission) -> None:
    """断言角色拥有指定权限。

    Raises:
        PermissionDenied: 角色不具备该权限时抛出。
    """
    if not has_permission(role, permission):
        raise PermissionDenied(f"{role.label}无权执行“{_permission_label(permission)}”")


def check_self_scope(actor_member_id: str, record_member_id: str) -> None:
    """断言操作只作用于自己提交的记录（REQ-006、REQ-007、REQ-010）。

    Raises:
        PermissionDenied: 操作对象属于其他成员时抛出。
    """
    if actor_member_id != record_member_id:
        raise PermissionDenied("只能操作自己提交的记录")


def can_manage_role(actor_role: Role, target_role: Role) -> bool:
    """判断操作者能否调整目标成员的角色（REQ-003）。

    * 创建者可以调整除自己以外的任何角色；
    * 管理员只能调整普通成员和只读成员，不能调整管理员。
    """
    if actor_role is Role.OWNER:
        return target_role is not Role.OWNER
    if actor_role is Role.ADMIN:
        return target_role in (Role.MEMBER, Role.READONLY)
    return False


def check_role_change(actor_role: Role, target_role: Role, new_role: Role) -> None:
    """断言角色调整合法。

    Raises:
        PermissionDenied: 调整目标或目标角色超出操作者权限时抛出。
    """
    check_permission(actor_role, Permission.CHANGE_MEMBER_ROLE)
    if not can_manage_role(actor_role, target_role):
        raise PermissionDenied(f"{actor_role.label}不能调整{target_role.label}的角色")
    if not can_manage_role(actor_role, new_role):
        raise PermissionDenied(f"{actor_role.label}不能把成员调整为{new_role.label}")
    if target_role is Role.OWNER:
        raise PermissionDenied("账本创建者的角色不可变更")


def check_invite_role(actor_role: Role, invited_role: Role) -> None:
    """断言邀请时赋予的角色不超出操作者权限。

    管理员只能邀请普通成员或只读成员；创建者可以邀请管理员。
    """
    check_permission(actor_role, Permission.INVITE_MEMBER)
    if invited_role is Role.OWNER:
        raise PermissionDenied("不能通过邀请产生第二个创建者")
    if invited_role is Role.ADMIN and actor_role is not Role.OWNER:
        raise PermissionDenied("只有创建者可以邀请管理员")


def _permission_label(permission: Permission) -> str:
    """返回权限项的中文描述，用于错误提示。"""
    return {
        Permission.VIEW_RECORDS: "查看记录",
        Permission.CREATE_RECORD: "新增记录",
        Permission.WITHDRAW_OWN_RECORD: "撤回记录",
        Permission.EDIT_OWN_RECORD: "修改记录",
        Permission.REVIEW_RECORD: "审核记录",
        Permission.VOID_RECORD: "作废记录",
        Permission.CORRECT_OWN_RECORD: "提交更正",
        Permission.VIEW_STATS: "查看统计",
        Permission.RUN_SETTLEMENT: "发起结算",
        Permission.INVITE_MEMBER: "邀请成员",
        Permission.CHANGE_MEMBER_ROLE: "调整角色",
        Permission.EDIT_LEDGER: "修改账本设置",
        Permission.VIEW_LOGS: "查看操作日志",
    }[permission]
