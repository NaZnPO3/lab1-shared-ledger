"""领域枚举。

约定：枚举值使用稳定的英文代码写入数据库，中文标签只用于界面展示，
这样数据库内容不会因为界面文案调整而失效。
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """成员在账本中的角色（REQ-003）。"""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    READONLY = "readonly"

    @property
    def label(self) -> str:
        """返回角色的中文名称。"""
        return _ROLE_LABELS[self]

    @classmethod
    def ordered(cls) -> tuple["Role", ...]:
        """按权限从高到低返回全部角色。"""
        return (cls.OWNER, cls.ADMIN, cls.MEMBER, cls.READONLY)


_ROLE_LABELS = {
    Role.OWNER: "创建者",
    Role.ADMIN: "管理员",
    Role.MEMBER: "普通成员",
    Role.READONLY: "只读成员",
}


class MemberStatus(str, Enum):
    """成员在账本中的在册状态（REQ-004、REQ-019）。"""

    ACTIVE = "active"
    LEFT = "left"

    @property
    def label(self) -> str:
        """返回状态的中文名称。"""
        return {MemberStatus.ACTIVE: "在册", MemberStatus.LEFT: "已退出"}[self]


class TxnType(str, Enum):
    """收支类型。"""

    INCOME = "income"
    EXPENSE = "expense"

    @property
    def label(self) -> str:
        """返回收支类型的中文名称。"""
        return {TxnType.INCOME: "收入", TxnType.EXPENSE: "支出"}[self]


class RecordStatus(str, Enum):
    """收支记录的审核状态（REQ-005 ~ REQ-010）。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    VOIDED = "voided"

    @property
    def label(self) -> str:
        """返回审核状态的中文名称。"""
        return {
            RecordStatus.PENDING: "待审核",
            RecordStatus.APPROVED: "已审核",
            RecordStatus.REJECTED: "已驳回",
            RecordStatus.WITHDRAWN: "已撤回",
            RecordStatus.VOIDED: "已作废",
        }[self]


class PeriodStatus(str, Enum):
    """结算周期状态（REQ-025）。"""

    OPEN = "open"
    SETTLED = "settled"

    @property
    def label(self) -> str:
        """返回结算周期状态的中文名称。"""
        return {PeriodStatus.OPEN: "进行中", PeriodStatus.SETTLED: "已结算"}[self]


class Permission(str, Enum):
    """需要判定的操作权限项。"""

    VIEW_RECORDS = "record.view"
    CREATE_RECORD = "record.create"
    WITHDRAW_OWN_RECORD = "record.withdraw"
    EDIT_OWN_RECORD = "record.edit"
    REVIEW_RECORD = "record.review"
    VOID_RECORD = "record.void"
    CORRECT_OWN_RECORD = "record.correct"
    VIEW_STATS = "stats.view"
    RUN_SETTLEMENT = "settlement.run"
    INVITE_MEMBER = "member.invite"
    CHANGE_MEMBER_ROLE = "member.change_role"
    EDIT_LEDGER = "ledger.edit"
    VIEW_LOGS = "logs.view"


class LogAction(str, Enum):
    """需要留痕的关键操作类型（REQ-018）。"""

    CREATE_LEDGER = "create_ledger"
    INVITE_MEMBER = "invite_member"
    CHANGE_ROLE = "change_role"
    LEAVE_LEDGER = "leave_ledger"
    CREATE_RECORD = "create_record"
    WITHDRAW_RECORD = "withdraw_record"
    EDIT_RECORD = "edit_record"
    APPROVE_RECORD = "approve_record"
    REJECT_RECORD = "reject_record"
    VOID_RECORD = "void_record"
    SUBMIT_CORRECTION = "submit_correction"
    APPROVE_CORRECTION = "approve_correction"
    SETTLE_PERIOD = "settle_period"
    SETTLE_FAILED = "settle_failed"
    UNAUTHORIZED = "unauthorized"

    @property
    def label(self) -> str:
        """返回操作类型的中文名称。"""
        return {
            LogAction.CREATE_LEDGER: "创建账本",
            LogAction.INVITE_MEMBER: "邀请成员",
            LogAction.CHANGE_ROLE: "调整角色",
            LogAction.LEAVE_LEDGER: "退出账本",
            LogAction.CREATE_RECORD: "新增记录",
            LogAction.WITHDRAW_RECORD: "撤回记录",
            LogAction.EDIT_RECORD: "修改重提",
            LogAction.APPROVE_RECORD: "审核通过",
            LogAction.REJECT_RECORD: "审核驳回",
            LogAction.VOID_RECORD: "作废记录",
            LogAction.SUBMIT_CORRECTION: "提交更正",
            LogAction.APPROVE_CORRECTION: "更正通过",
            LogAction.SETTLE_PERIOD: "周期结算",
            LogAction.SETTLE_FAILED: "结算失败",
            LogAction.UNAUTHORIZED: "越权请求",
        }[self]


class LogResult(str, Enum):
    """操作日志的处理结果。"""

    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"

    @property
    def label(self) -> str:
        """返回处理结果的中文名称。"""
        return {
            LogResult.SUCCESS: "成功",
            LogResult.DENIED: "已拒绝",
            LogResult.FAILED: "失败",
        }[self]
