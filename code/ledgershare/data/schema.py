"""数据库结构定义。

建表 SQL 以模块常量形式内嵌，打包成 exe 时不会因为漏拷 .sql 文件而失败。
表结构与实验二类图对应关系见各表注释。
"""

from __future__ import annotations

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- 用户：UML User
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

-- 账本：UML Ledger。金额上限以分存储（REQ-015）
CREATE TABLE IF NOT EXISTS ledgers (
    ledger_id          TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    amount_limit_cents INTEGER NOT NULL,
    created_by         TEXT NOT NULL REFERENCES users(user_id),
    next_period_seq    INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL
);

-- 成员：UML Member。角色挂在成员上，同一用户在不同账本角色不同
CREATE TABLE IF NOT EXISTS members (
    member_id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(ledger_id) ON DELETE CASCADE,
    user_id   TEXT NOT NULL REFERENCES users(user_id),
    role      TEXT NOT NULL,
    status    TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    left_at   TEXT,
    UNIQUE (ledger_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);
CREATE INDEX IF NOT EXISTS idx_members_ledger ON members(ledger_id, status);

-- 分类：UML Category
CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    ledger_id   TEXT NOT NULL REFERENCES ledgers(ledger_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    applies_to  TEXT NOT NULL,
    UNIQUE (ledger_id, name, applies_to)
);

-- 结算周期：UML SettlementPeriod。结算后锁定（REQ-025）
CREATE TABLE IF NOT EXISTS settlement_periods (
    period_id  TEXT PRIMARY KEY,
    ledger_id  TEXT NOT NULL REFERENCES ledgers(ledger_id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT,
    status     TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE (ledger_id, seq)
);

-- 收支记录：UML TransactionRecord。
-- version 用于乐观锁，并发修改时后提交者失败（REQ-017）
CREATE TABLE IF NOT EXISTS txn_records (
    record_id          TEXT PRIMARY KEY,
    ledger_id          TEXT NOT NULL REFERENCES ledgers(ledger_id) ON DELETE CASCADE,
    period_id          TEXT NOT NULL REFERENCES settlement_periods(period_id),
    member_id          TEXT NOT NULL REFERENCES members(member_id),
    category_id        TEXT NOT NULL REFERENCES categories(category_id),
    amount_cents       INTEGER NOT NULL,
    txn_type           TEXT NOT NULL,
    occurred_on        TEXT NOT NULL,
    note               TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL,
    corrects_record_id TEXT REFERENCES txn_records(record_id),
    version            INTEGER NOT NULL DEFAULT 1,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_ledger_date
    ON txn_records(ledger_id, occurred_on DESC);
CREATE INDEX IF NOT EXISTS idx_records_ledger_status
    ON txn_records(ledger_id, status);
CREATE INDEX IF NOT EXISTS idx_records_period
    ON txn_records(period_id, status);
CREATE INDEX IF NOT EXISTS idx_records_member
    ON txn_records(member_id);

-- 结算结果：一个结算周期内每个成员一行
CREATE TABLE IF NOT EXISTS settlements (
    settlement_id  TEXT PRIMARY KEY,
    period_id      TEXT NOT NULL REFERENCES settlement_periods(period_id),
    ledger_id      TEXT NOT NULL REFERENCES ledgers(ledger_id) ON DELETE CASCADE,
    member_id      TEXT NOT NULL REFERENCES members(member_id),
    paid_cents     INTEGER NOT NULL,
    share_cents    INTEGER NOT NULL,
    balance_cents  INTEGER NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_settlements_period
    ON settlements(period_id);

-- 操作日志：UML OperationLog，只追加（REQ-018）
CREATE TABLE IF NOT EXISTS operation_logs (
    log_id          TEXT PRIMARY KEY,
    ledger_id       TEXT,
    actor_user_id   TEXT NOT NULL,
    actor_member_id TEXT,
    action          TEXT NOT NULL,
    target_type     TEXT,
    target_id       TEXT,
    result          TEXT NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_ledger_time
    ON operation_logs(ledger_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_action
    ON operation_logs(action);

-- 幂等键：同一用户同一请求只产生一次业务记录（REQ-016）
CREATE TABLE IF NOT EXISTS idempotency_keys (
    user_id      TEXT NOT NULL,
    idem_key     TEXT NOT NULL,
    action       TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    record_id    TEXT,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, idem_key)
);
"""
