"""数据访问层。

仓储对象只负责 SQL，不含业务判断；每个仓储在构造时接收一个连接，
由服务层决定事务边界，这样"写业务数据 + 写日志 + 记幂等键"能在同一事务内完成。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

import sqlite3

from ..enums import MemberStatus, PeriodStatus, RecordStatus, Role, TxnType
from ..models import (
    Category,
    Ledger,
    Member,
    OperationLogEntry,
    RecordView,
    SettlementLine,
    SettlementPeriod,
    TransactionRecord,
    User,
)
from ..timeutil import to_date_text, to_text


class UserRepository:
    """``users`` 表的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        user_id: str,
        username: str,
        display_name: str,
        password_hash: str,
        salt: str,
        created_at: datetime,
    ) -> None:
        """插入新用户。"""
        self._conn.execute(
            "INSERT INTO users (user_id, username, display_name, password_hash,"
            " salt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, display_name, password_hash, salt, to_text(created_at)),
        )

    def by_username(self, username: str) -> sqlite3.Row | None:
        """按账号查询原始行（含密码散列，仅供认证服务使用）。"""
        return self._conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    def by_id(self, user_id: str) -> User | None:
        """按用户 ID 查询实体。"""
        row = self._conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return User.from_row(row) if row else None

    def exists(self, username: str) -> bool:
        """判断账号是否已被占用。"""
        row = self._conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row is not None


class LedgerRepository:
    """``ledgers`` 表的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        ledger_id: str,
        name: str,
        amount_limit_cents: int,
        created_by: str,
        created_at: datetime,
    ) -> None:
        """插入新账本。"""
        self._conn.execute(
            "INSERT INTO ledgers (ledger_id, name, amount_limit_cents, created_by,"
            " next_period_seq, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (ledger_id, name, amount_limit_cents, created_by, to_text(created_at)),
        )

    def by_id(self, ledger_id: str) -> Ledger | None:
        """按 ID 查询账本。"""
        row = self._conn.execute(
            "SELECT * FROM ledgers WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        return Ledger.from_row(row) if row else None

    def list_for_user(self, user_id: str) -> list[Ledger]:
        """列出用户仍然在册的账本。"""
        rows = self._conn.execute(
            "SELECT l.* FROM ledgers l JOIN members m ON m.ledger_id = l.ledger_id"
            " WHERE m.user_id = ? AND m.status = ? ORDER BY l.created_at DESC",
            (user_id, MemberStatus.ACTIVE.value),
        ).fetchall()
        return [Ledger.from_row(row) for row in rows]

    def update_amount_limit(self, ledger_id: str, amount_limit_cents: int) -> None:
        """调整账本金额上限（REQ-015）。"""
        self._conn.execute(
            "UPDATE ledgers SET amount_limit_cents = ? WHERE ledger_id = ?",
            (amount_limit_cents, ledger_id),
        )

    def take_next_period_seq(self, ledger_id: str) -> int:
        """取出并递增账本的周期序号，返回本次可用的序号。"""
        row = self._conn.execute(
            "SELECT next_period_seq FROM ledgers WHERE ledger_id = ?", (ledger_id,)
        ).fetchone()
        seq = int(row["next_period_seq"]) if row else 1
        self._conn.execute(
            "UPDATE ledgers SET next_period_seq = ? WHERE ledger_id = ?",
            (seq + 1, ledger_id),
        )
        return seq


class MemberRepository:
    """``members`` 表的读写。"""

    _SELECT = (
        "SELECT m.*, u.username AS username, u.display_name AS display_name"
        " FROM members m JOIN users u ON u.user_id = m.user_id"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        member_id: str,
        ledger_id: str,
        user_id: str,
        role: Role,
        joined_at: datetime,
    ) -> None:
        """插入新成员。"""
        self._conn.execute(
            "INSERT INTO members (member_id, ledger_id, user_id, role, status,"
            " joined_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                member_id,
                ledger_id,
                user_id,
                role.value,
                MemberStatus.ACTIVE.value,
                to_text(joined_at),
            ),
        )

    def by_id(self, member_id: str) -> Member | None:
        """按成员 ID 查询。"""
        row = self._conn.execute(
            f"{self._SELECT} WHERE m.member_id = ?", (member_id,)
        ).fetchone()
        return Member.from_row(row) if row else None

    def by_ledger_and_user(self, ledger_id: str, user_id: str) -> Member | None:
        """查询某用户在某账本中的成员身份。"""
        row = self._conn.execute(
            f"{self._SELECT} WHERE m.ledger_id = ? AND m.user_id = ?",
            (ledger_id, user_id),
        ).fetchone()
        return Member.from_row(row) if row else None

    def list_by_ledger(self, ledger_id: str) -> list[Member]:
        """列出账本全部成员（含已退出，用于历史记录展示）。"""
        rows = self._conn.execute(
            f"{self._SELECT} WHERE m.ledger_id = ?"
            " ORDER BY m.status ASC, m.joined_at ASC",
            (ledger_id,),
        ).fetchall()
        return [Member.from_row(row) for row in rows]

    def list_active(self, ledger_id: str) -> list[Member]:
        """列出仍在册的成员。"""
        rows = self._conn.execute(
            f"{self._SELECT} WHERE m.ledger_id = ? AND m.status = ?"
            " ORDER BY m.joined_at ASC",
            (ledger_id, MemberStatus.ACTIVE.value),
        ).fetchall()
        return [Member.from_row(row) for row in rows]

    def count_active(self, ledger_id: str) -> int:
        """统计在册成员数量。"""
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM members WHERE ledger_id = ? AND status = ?",
            (ledger_id, MemberStatus.ACTIVE.value),
        ).fetchone()
        return int(row["total"]) if row else 0

    def update_role(self, member_id: str, role: Role) -> None:
        """调整成员角色（REQ-003）。"""
        self._conn.execute(
            "UPDATE members SET role = ? WHERE member_id = ?",
            (role.value, member_id),
        )

    def mark_left(self, member_id: str, left_at: datetime) -> None:
        """把成员标记为已退出并记录退出时间（REQ-004）。"""
        self._conn.execute(
            "UPDATE members SET status = ?, left_at = ? WHERE member_id = ?",
            (MemberStatus.LEFT.value, to_text(left_at), member_id),
        )

    def reactivate(self, member_id: str, role: Role, joined_at: datetime) -> None:
        """让已退出的成员重新加入，保留原 ``member_id`` 及其历史记录（REQ-019）。"""
        self._conn.execute(
            "UPDATE members SET status = ?, left_at = NULL, role = ?, joined_at = ?"
            " WHERE member_id = ?",
            (MemberStatus.ACTIVE.value, role.value, to_text(joined_at), member_id),
        )


class CategoryRepository:
    """``categories`` 表的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self, category_id: str, ledger_id: str, name: str, applies_to: TxnType
    ) -> None:
        """插入一个分类。"""
        self._conn.execute(
            "INSERT INTO categories (category_id, ledger_id, name, applies_to)"
            " VALUES (?, ?, ?, ?)",
            (category_id, ledger_id, name, applies_to.value),
        )

    def list_by_ledger(self, ledger_id: str) -> list[Category]:
        """列出账本的分类，支出在前收入在后。"""
        rows = self._conn.execute(
            "SELECT * FROM categories WHERE ledger_id = ?"
            " ORDER BY applies_to DESC, name ASC",
            (ledger_id,),
        ).fetchall()
        return [Category.from_row(row) for row in rows]

    def map_by_id(self, ledger_id: str) -> dict[str, Category]:
        """返回 ``{分类 ID: 分类}``，供校验快速查找。"""
        return {item.category_id: item for item in self.list_by_ledger(ledger_id)}


class PeriodRepository:
    """``settlement_periods`` 表的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        period_id: str,
        ledger_id: str,
        seq: int,
        start_date: date,
        status: PeriodStatus = PeriodStatus.OPEN,
    ) -> None:
        """插入一个结算周期。"""
        self._conn.execute(
            "INSERT INTO settlement_periods (period_id, ledger_id, seq, start_date,"
            " end_date, status) VALUES (?, ?, ?, ?, NULL, ?)",
            (period_id, ledger_id, seq, to_date_text(start_date), status.value),
        )

    def by_id(self, period_id: str) -> SettlementPeriod | None:
        """按 ID 查询周期。"""
        row = self._conn.execute(
            "SELECT * FROM settlement_periods WHERE period_id = ?", (period_id,)
        ).fetchone()
        return SettlementPeriod.from_row(row) if row else None

    def current_open(self, ledger_id: str) -> SettlementPeriod | None:
        """返回账本当前进行中的周期。"""
        row = self._conn.execute(
            "SELECT * FROM settlement_periods WHERE ledger_id = ? AND status = ?"
            " ORDER BY seq DESC LIMIT 1",
            (ledger_id, PeriodStatus.OPEN.value),
        ).fetchone()
        return SettlementPeriod.from_row(row) if row else None

    def list_by_ledger(self, ledger_id: str) -> list[SettlementPeriod]:
        """按序号列出账本的全部周期。"""
        rows = self._conn.execute(
            "SELECT * FROM settlement_periods WHERE ledger_id = ? ORDER BY seq DESC",
            (ledger_id,),
        ).fetchall()
        return [SettlementPeriod.from_row(row) for row in rows]

    def mark_settled(
        self, period_id: str, end_date: date, settled_at: datetime
    ) -> None:
        """把周期标记为已结算并写入结束日期（REQ-025）。"""
        self._conn.execute(
            "UPDATE settlement_periods SET status = ?, end_date = ?, settled_at = ?"
            " WHERE period_id = ? AND status = ?",
            (
                PeriodStatus.SETTLED.value,
                to_date_text(end_date),
                to_text(settled_at),
                period_id,
                PeriodStatus.OPEN.value,
            ),
        )


class RecordRepository:
    """``txn_records`` 表的读写，含乐观锁更新。"""

    _VIEW_SELECT = (
        "SELECT r.*, u.display_name AS member_name, c.name AS category_name"
        " FROM txn_records r"
        " JOIN members m ON m.member_id = r.member_id"
        " JOIN users u ON u.user_id = m.user_id"
        " JOIN categories c ON c.category_id = r.category_id"
    )

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        record_id: str,
        ledger_id: str,
        period_id: str,
        member_id: str,
        category_id: str,
        amount_cents: int,
        txn_type: TxnType,
        occurred_on: date,
        note: str,
        status: RecordStatus,
        created_at: datetime,
        corrects_record_id: str | None = None,
    ) -> None:
        """插入一条收支记录，初始版本号为 1。"""
        stamp = to_text(created_at)
        self._conn.execute(
            "INSERT INTO txn_records (record_id, ledger_id, period_id, member_id,"
            " category_id, amount_cents, txn_type, occurred_on, note, status,"
            " corrects_record_id, version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                record_id,
                ledger_id,
                period_id,
                member_id,
                category_id,
                amount_cents,
                txn_type.value,
                to_date_text(occurred_on),
                note,
                status.value,
                corrects_record_id,
                stamp,
                stamp,
            ),
        )

    def by_id(self, record_id: str) -> TransactionRecord | None:
        """按记录 ID 查询。"""
        row = self._conn.execute(
            "SELECT * FROM txn_records WHERE record_id = ?", (record_id,)
        ).fetchone()
        return TransactionRecord.from_row(row) if row else None

    def view_by_id(self, record_id: str) -> RecordView | None:
        """按记录 ID 查询联表视图。"""
        row = self._conn.execute(
            f"{self._VIEW_SELECT} WHERE r.record_id = ?", (record_id,)
        ).fetchone()
        return RecordView.from_row(row) if row else None

    def list_views(
        self,
        ledger_id: str,
        *,
        statuses: Sequence[RecordStatus] | None = None,
        member_id: str | None = None,
        category_ids: Sequence[str] | None = None,
        txn_type: TxnType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        amount_min_cents: int | None = None,
        amount_max_cents: int | None = None,
        keyword: str | None = None,
        period_id: str | None = None,
        limit: int | None = None,
    ) -> list[RecordView]:
        """按条件查询记录（REQ-011）。

        Args:
            ledger_id: 必填，限定账本。
            statuses: 状态白名单。
            member_id: 记录人筛选。
            category_ids: 分类白名单。
            txn_type: 收支类型筛选。
            date_from: 发生日期下界（含）。
            date_to: 发生日期上界（含）。
            amount_min_cents: 金额下界（含）。
            amount_max_cents: 金额上界（含）。
            keyword: 备注模糊匹配。
            period_id: 结算周期筛选。
            limit: 最大返回条数。

        Returns:
            符合条件的记录视图列表，按发生日期倒序、创建时间倒序排列。
        """
        sql = [f"{self._VIEW_SELECT} WHERE r.ledger_id = ?"]
        params: list[Any] = [ledger_id]

        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql.append(f"AND r.status IN ({placeholders})")
            params.extend(status.value for status in statuses)
        if member_id:
            sql.append("AND r.member_id = ?")
            params.append(member_id)
        if category_ids:
            placeholders = ",".join("?" for _ in category_ids)
            sql.append(f"AND r.category_id IN ({placeholders})")
            params.extend(category_ids)
        if txn_type is not None:
            sql.append("AND r.txn_type = ?")
            params.append(txn_type.value)
        if date_from is not None:
            sql.append("AND r.occurred_on >= ?")
            params.append(to_date_text(date_from))
        if date_to is not None:
            sql.append("AND r.occurred_on <= ?")
            params.append(to_date_text(date_to))
        if amount_min_cents is not None:
            sql.append("AND r.amount_cents >= ?")
            params.append(amount_min_cents)
        if amount_max_cents is not None:
            sql.append("AND r.amount_cents <= ?")
            params.append(amount_max_cents)
        if keyword:
            sql.append("AND r.note LIKE ?")
            params.append(f"%{keyword}%")
        if period_id:
            sql.append("AND r.period_id = ?")
            params.append(period_id)

        sql.append("ORDER BY r.occurred_on DESC, r.created_at DESC")
        if limit:
            sql.append("LIMIT ?")
            params.append(limit)

        rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [RecordView.from_row(row) for row in rows]

    def update_content(
        self,
        record_id: str,
        *,
        amount_cents: int,
        txn_type: TxnType,
        category_id: str,
        occurred_on: date,
        note: str,
        expected_status: RecordStatus,
        expected_version: int,
        updated_at: datetime,
        new_status: RecordStatus,
    ) -> bool:
        """更新记录内容并推进版本号；返回是否命中（REQ-007、REQ-017）。"""
        cursor = self._conn.execute(
            "UPDATE txn_records SET amount_cents = ?, txn_type = ?, category_id = ?,"
            " occurred_on = ?, note = ?, status = ?, version = version + 1,"
            " updated_at = ? WHERE record_id = ? AND status = ? AND version = ?",
            (
                amount_cents,
                txn_type.value,
                category_id,
                to_date_text(occurred_on),
                note,
                new_status.value,
                to_text(updated_at),
                record_id,
                expected_status.value,
                expected_version,
            ),
        )
        return cursor.rowcount == 1

    def update_status(
        self,
        record_id: str,
        *,
        expected_status: RecordStatus,
        new_status: RecordStatus,
        expected_version: int,
        updated_at: datetime,
    ) -> bool:
        """以乐观锁方式变更记录状态；返回是否命中（REQ-017）。"""
        cursor = self._conn.execute(
            "UPDATE txn_records SET status = ?, version = version + 1, updated_at = ?"
            " WHERE record_id = ? AND status = ? AND version = ?",
            (
                new_status.value,
                to_text(updated_at),
                record_id,
                expected_status.value,
                expected_version,
            ),
        )
        return cursor.rowcount == 1

    def list_in_period(
        self, period_id: str, statuses: Sequence[RecordStatus]
    ) -> list[TransactionRecord]:
        """列出某周期内指定状态的记录。"""
        placeholders = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT * FROM txn_records WHERE period_id = ? AND status IN"
            f" ({placeholders}) ORDER BY occurred_on ASC",
            [period_id, *(status.value for status in statuses)],
        ).fetchall()
        return [TransactionRecord.from_row(row) for row in rows]

    def count_in_period(self, period_id: str) -> int:
        """统计某周期内的记录总数。"""
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM txn_records WHERE period_id = ?",
            (period_id,),
        ).fetchone()
        return int(row["total"]) if row else 0

    def count_in_period_for_member(
        self,
        period_id: str,
        member_id: str,
        statuses: Sequence[RecordStatus],
    ) -> int:
        """统计某成员在某周期内指定状态的记录数（用于退出校验，REQ-004）。"""
        placeholders = ",".join("?" for _ in statuses)
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM txn_records WHERE period_id = ?"
            f" AND member_id = ? AND status IN ({placeholders})",
            [period_id, member_id, *(status.value for status in statuses)],
        ).fetchone()
        return int(row["total"]) if row else 0

    def count_by_status(self, ledger_id: str) -> dict[str, int]:
        """按状态统计账本记录数量，供界面显示待办数量。"""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS total FROM txn_records WHERE ledger_id = ?"
            " GROUP BY status",
            (ledger_id,),
        ).fetchall()
        return {row["status"]: int(row["total"]) for row in rows}

    def sum_amount(
        self,
        ledger_id: str,
        *,
        statuses: Sequence[RecordStatus],
        date_from: date | None = None,
        date_to: date | None = None,
        period_id: str | None = None,
    ) -> int:
        """按状态与日期范围汇总金额（分）。"""
        placeholders = ",".join("?" for _ in statuses)
        sql = [
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM txn_records",
            f"WHERE ledger_id = ? AND status IN ({placeholders})",
        ]
        params: list[Any] = [ledger_id, *(status.value for status in statuses)]
        if date_from is not None:
            sql.append("AND occurred_on >= ?")
            params.append(to_date_text(date_from))
        if date_to is not None:
            sql.append("AND occurred_on <= ?")
            params.append(to_date_text(date_to))
        if period_id is not None:
            sql.append("AND period_id = ?")
            params.append(period_id)
        row = self._conn.execute(" ".join(sql), params).fetchone()
        return int(row["total"]) if row else 0

    def group_sum(
        self,
        ledger_id: str,
        *,
        statuses: Sequence[RecordStatus],
        group_by: str,
    ) -> list[Mapping[str, Any]]:
        """按成员或分类分组汇总收支（REQ-013）。

        Args:
            ledger_id: 账本 ID。
            statuses: 纳入统计的状态。
            group_by: 只接受 ``"member"`` 或 ``"category"``。

        Returns:
            每行包含分组键、收支类型与小计金额。
        """
        if group_by == "member":
            key_column = "r.member_id"
            join = (
                " JOIN members m ON m.member_id = r.member_id"
                " JOIN users u ON u.user_id = m.user_id"
            )
            name_column = "u.display_name AS group_name"
        elif group_by == "category":
            key_column = "r.category_id"
            join = " JOIN categories c ON c.category_id = r.category_id"
            name_column = "c.name AS group_name"
        else:
            raise ValueError("group_by 只支持 member 或 category")

        placeholders = ",".join("?" for _ in statuses)
        sql = (
            f"SELECT {key_column} AS group_id, {name_column}, r.txn_type AS txn_type,"
            " COUNT(*) AS total, COALESCE(SUM(r.amount_cents), 0) AS amount"
            " FROM txn_records r"
            f"{join}"
            f" WHERE r.ledger_id = ? AND r.status IN ({placeholders})"
            " GROUP BY group_id, r.txn_type ORDER BY group_name ASC"
        )
        return list(
            self._conn.execute(
                sql, [ledger_id, *(status.value for status in statuses)]
            ).fetchall()
        )


class SettlementRepository:
    """``settlements`` 表的读写。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_many(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """批量写入结算结果。"""
        self._conn.executemany(
            "INSERT INTO settlements (settlement_id, period_id, ledger_id, member_id,"
            " paid_cents, share_cents, balance_cents, created_at)"
            " VALUES (:settlement_id, :period_id, :ledger_id, :member_id,"
            " :paid_cents, :share_cents, :balance_cents, :created_at)",
            list(rows),
        )

    def list_by_period(self, period_id: str) -> list[SettlementLine]:
        """列出某周期的结算结果，附带成员名称。"""
        rows = self._conn.execute(
            "SELECT s.*, u.display_name AS member_name FROM settlements s"
            " JOIN members m ON m.member_id = s.member_id"
            " JOIN users u ON u.user_id = m.user_id"
            " WHERE s.period_id = ? ORDER BY s.balance_cents DESC",
            (period_id,),
        ).fetchall()
        return [SettlementLine.from_row(row) for row in rows]

    def count_by_period(self, period_id: str) -> int:
        """统计某周期已写入的结算行数。"""
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM settlements WHERE period_id = ?",
            (period_id,),
        ).fetchone()
        return int(row["total"]) if row else 0


class LogRepository:
    """``operation_logs`` 表的读写，只追加不修改（REQ-018）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(
        self,
        *,
        log_id: str,
        ledger_id: str | None,
        actor_user_id: str,
        actor_member_id: str | None,
        action: str,
        target_type: str | None,
        target_id: str | None,
        result: str,
        detail: str,
        created_at: datetime,
    ) -> None:
        """追加一条操作日志。"""
        self._conn.execute(
            "INSERT INTO operation_logs (log_id, ledger_id, actor_user_id,"
            " actor_member_id, action, target_type, target_id, result, detail,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                log_id,
                ledger_id,
                actor_user_id,
                actor_member_id,
                action,
                target_type,
                target_id,
                result,
                detail,
                to_text(created_at),
            ),
        )

    def list_by_ledger(self, ledger_id: str, limit: int = 200) -> list[OperationLogEntry]:
        """列出账本最近的操作日志。"""
        rows = self._conn.execute(
            "SELECT * FROM operation_logs WHERE ledger_id = ?"
            " ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (ledger_id, limit),
        ).fetchall()
        return [OperationLogEntry.from_row(row) for row in rows]

    def count(self, *, ledger_id: str | None = None, action: str | None = None) -> int:
        """统计日志条数，供测试与界面使用。"""
        sql = ["SELECT COUNT(*) AS total FROM operation_logs WHERE 1 = 1"]
        params: list[Any] = []
        if ledger_id is not None:
            sql.append("AND ledger_id = ?")
            params.append(ledger_id)
        if action is not None:
            sql.append("AND action = ?")
            params.append(action)
        row = self._conn.execute(" ".join(sql), params).fetchone()
        return int(row["total"]) if row else 0


class IdempotencyRepository:
    """``idempotency_keys`` 表的读写（REQ-016）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find(self, user_id: str, idem_key: str) -> sqlite3.Row | None:
        """查询已保存的幂等记录。"""
        return self._conn.execute(
            "SELECT * FROM idempotency_keys WHERE user_id = ? AND idem_key = ?",
            (user_id, idem_key),
        ).fetchone()

    def save(
        self,
        *,
        user_id: str,
        idem_key: str,
        action: str,
        request_hash: str,
        record_id: str | None,
        created_at: datetime,
    ) -> None:
        """保存幂等键与首次请求的结果。"""
        self._conn.execute(
            "INSERT INTO idempotency_keys (user_id, idem_key, action, request_hash,"
            " record_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, idem_key, action, request_hash, record_id, to_text(created_at)),
        )
