"""领域异常。

服务层用异常表达"业务规则不允许"，界面层据 ``code`` 分类展示并决定
是否需要提示用户刷新（例如 :class:`StateConflict`）。
"""

from __future__ import annotations


class LedgerError(Exception):
    """所有业务异常的基类。"""

    code = "ledger.error"
    default_message = "操作失败"

    def __init__(self, message: str = "", *, detail: str = "") -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.detail = detail

    def __str__(self) -> str:
        return self.message


class ValidationError(LedgerError):
    """必填字段缺失、格式非法等输入校验失败（REQ-005、REQ-015）。"""

    code = "validation.error"
    default_message = "输入内容不合法"


class PermissionDenied(LedgerError):
    """角色或账本权限不足（REQ-003、REQ-020）。"""

    code = "permission.denied"
    default_message = "无权限执行该操作"


class StateConflict(LedgerError):
    """记录或周期状态已变化，本次操作基于过期状态（REQ-017、REQ-025）。"""

    code = "state.conflict"
    default_message = "记录状态已变化，请刷新后重试"


class NotFound(LedgerError):
    """目标对象不存在或当前用户不可见。"""

    code = "object.not_found"
    default_message = "找不到目标对象"


class DuplicateError(LedgerError):
    """唯一性约束被破坏，例如重复邀请同一用户。"""

    code = "object.duplicate"
    default_message = "目标对象已存在"


class SettlementError(LedgerError):
    """结算过程中的业务失败，需要回滚并记录失败日志（REQ-021）。"""

    code = "settlement.failed"
    default_message = "结算失败"


class AuthError(LedgerError):
    """注册或登录失败。"""

    code = "auth.failed"
    default_message = "账号或密码错误"
