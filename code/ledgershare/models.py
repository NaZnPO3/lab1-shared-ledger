"""领域实体。

实体与实验二 UML 类图一一对应（``User``、``Ledger``、``Member``、``Category``、
``TransactionRecord``、``SettlementPeriod``、``OperationLog``），另外补充了
``SettlementLine`` 承载结算结果。实体本身不访问数据库，只负责承载数据，
业务方法由服务层实现，保持存储无关。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

from .enums import MemberStatus, PeriodStatus, RecordStatus, Role, TxnType
from .money import format_cents
from .timeutil import parse_date, parse_datetime


@dataclass(frozen=True, slots=True)
class User:
    """系统用户（UML ``User``）。"""

    user_id: str
    username: str
    display_name: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "User":
        """从数据库行构造实体。"""
        return cls(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            created_at=parse_datetime(row["created_at"]) or datetime.min,
        )


@dataclass(frozen=True, slots=True)
class Ledger:
    """账本（UML ``Ledger``）。"""

    ledger_id: str
    name: str
    amount_limit_cents: int
    created_by: str
    next_period_seq: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Ledger":
        """从数据库行构造实体。"""
        return cls(
            ledger_id=row["ledger_id"],
            name=row["name"],
            amount_limit_cents=int(row["amount_limit_cents"]),
            created_by=row["created_by"],
            next_period_seq=int(row["next_period_seq"]),
            created_at=parse_datetime(row["created_at"]) or datetime.min,
        )

    @property
    def amount_limit_text(self) -> str:
        """返回便于阅读的金额上限。"""
        return format_cents(self.amount_limit_cents)


@dataclass(frozen=True, slots=True)
class Member:
    """账本成员（UML ``Member``）：角色挂在成员而非用户上。"""

    member_id: str
    ledger_id: str
    user_id: str
    role: Role
    status: MemberStatus
    joined_at: datetime
    left_at: datetime | None = None
    display_name: str = ""
    username: str = ""

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Member":
        """从数据库行构造实体（可选字段来自 users 表连接）。"""
        keys = set(row.keys())
        return cls(
            member_id=row["member_id"],
            ledger_id=row["ledger_id"],
            user_id=row["user_id"],
            role=Role(row["role"]),
            status=MemberStatus(row["status"]),
            joined_at=parse_datetime(row["joined_at"]) or datetime.min,
            left_at=parse_datetime(row["left_at"]),
            display_name=row["display_name"] if "display_name" in keys else "",
            username=row["username"] if "username" in keys else "",
        )

    @property
    def is_active(self) -> bool:
        """成员当前是否在册。"""
        return self.status is MemberStatus.ACTIVE

    @property
    def display(self) -> str:
        """界面上展示成员用的名称。"""
        return self.display_name or self.username or self.member_id

    @property
    def role_label(self) -> str:
        """角色中文名称。"""
        return self.role.label


@dataclass(frozen=True, slots=True)
class Category:
    """收支分类（UML ``Category``）。"""

    category_id: str
    ledger_id: str
    name: str
    applies_to: TxnType

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Category":
        """从数据库行构造实体。"""
        return cls(
            category_id=row["category_id"],
            ledger_id=row["ledger_id"],
            name=row["name"],
            applies_to=TxnType(row["applies_to"]),
        )


@dataclass(frozen=True, slots=True)
class SettlementPeriod:
    """结算周期（UML ``SettlementPeriod``，对应 REQ-025 的锁定对象）。"""

    period_id: str
    ledger_id: str
    seq: int
    start_date: date
    end_date: date | None
    status: PeriodStatus
    settled_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "SettlementPeriod":
        """从数据库行构造实体。"""
        return cls(
            period_id=row["period_id"],
            ledger_id=row["ledger_id"],
            seq=int(row["seq"]),
            start_date=parse_date(row["start_date"]) or date.min,
            end_date=parse_date(row["end_date"]),
            status=PeriodStatus(row["status"]),
            settled_at=parse_datetime(row["settled_at"]),
        )

    @property
    def is_open(self) -> bool:
        """周期是否仍处于进行中。"""
        return self.status is PeriodStatus.OPEN

    @property
    def range_text(self) -> str:
        """周期的可读区间描述。"""
        if self.status is PeriodStatus.OPEN:
            return f"第 {self.seq} 期（{self.start_date} 起，进行中）"
        return f"第 {self.seq} 期（{self.start_date} ~ {self.end_date}，已结算）"


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    """收支记录（UML ``TransactionRecord``）。"""

    record_id: str
    ledger_id: str
    period_id: str
    member_id: str
    category_id: str
    amount_cents: int
    txn_type: TxnType
    occurred_on: date
    note: str
    status: RecordStatus
    version: int
    created_at: datetime
    updated_at: datetime
    corrects_record_id: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "TransactionRecord":
        """从数据库行构造实体。"""
        return cls(
            record_id=row["record_id"],
            ledger_id=row["ledger_id"],
            period_id=row["period_id"],
            member_id=row["member_id"],
            category_id=row["category_id"],
            amount_cents=int(row["amount_cents"]),
            txn_type=TxnType(row["txn_type"]),
            occurred_on=parse_date(row["occurred_on"]) or date.min,
            note=row["note"] or "",
            status=RecordStatus(row["status"]),
            version=int(row["version"]),
            created_at=parse_datetime(row["created_at"]) or datetime.min,
            updated_at=parse_datetime(row["updated_at"]) or datetime.min,
            corrects_record_id=row["corrects_record_id"],
        )

    @property
    def amount_text(self) -> str:
        """金额的可读文本。"""
        return format_cents(self.amount_cents)

    @property
    def is_editable_by_recorder(self) -> bool:
        """原记录人当前是否可以修改该记录（仅已驳回状态可改）。"""
        return self.status is RecordStatus.REJECTED

    @property
    def can_be_withdrawn(self) -> bool:
        """是否处于可撤回状态。"""
        return self.status is RecordStatus.PENDING


@dataclass(frozen=True, slots=True)
class RecordView:
    """记录列表展示用的联表视图，附带成员与分类名称。"""

    record: TransactionRecord
    member_name: str
    category_name: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "RecordView":
        """从联表查询结果构造视图。"""
        return cls(
            record=TransactionRecord.from_row(row),
            member_name=row["member_name"] or "",
            category_name=row["category_name"] or "",
        )


@dataclass(frozen=True, slots=True)
class SettlementLine:
    """结算结果中某个成员的一行。"""

    settlement_id: str
    period_id: str
    ledger_id: str
    member_id: str
    paid_cents: int
    share_cents: int
    balance_cents: int
    member_name: str = ""

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "SettlementLine":
        """从数据库行构造实体。"""
        keys = set(row.keys())
        return cls(
            settlement_id=row["settlement_id"],
            period_id=row["period_id"],
            ledger_id=row["ledger_id"],
            member_id=row["member_id"],
            paid_cents=int(row["paid_cents"]),
            share_cents=int(row["share_cents"]),
            balance_cents=int(row["balance_cents"]),
            member_name=row["member_name"] if "member_name" in keys else "",
        )


@dataclass(frozen=True, slots=True)
class SettlementSummary:
    """一次结算的完整结果，供界面与日志使用。"""

    period: SettlementPeriod
    lines: tuple[SettlementLine, ...] = field(default_factory=tuple)
    total_expense_cents: int = 0
    total_income_cents: int = 0

    @property
    def is_empty(self) -> bool:
        """本次结算是否没有任何成员数据。"""
        return not self.lines


@dataclass(frozen=True, slots=True)
class OperationLogEntry:
    """操作日志（UML ``OperationLog``，只追加）。"""

    log_id: str
    ledger_id: str | None
    actor_user_id: str
    actor_member_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    result: str
    detail: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "OperationLogEntry":
        """从数据库行构造实体。"""
        return cls(
            log_id=row["log_id"],
            ledger_id=row["ledger_id"],
            actor_user_id=row["actor_user_id"],
            actor_member_id=row["actor_member_id"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            result=row["result"],
            detail=row["detail"] or "",
            created_at=parse_datetime(row["created_at"]) or datetime.min,
        )
