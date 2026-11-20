"""幂等与并发测试（REQ-016、REQ-017）。"""

from __future__ import annotations

import threading

import pytest

from ledgershare.data.database import Database
from ledgershare.enums import LogAction, RecordStatus
from ledgershare.errors import LedgerError, ValidationError


def test_repeat_submit_returns_same_record(scenario, app, payload) -> None:
    """同一幂等键重复提交只产生一条记录、一条日志（REQ-016）。"""
    first = app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload(amount="66"), idem_key="k-1"
    )
    second = app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload(amount="66"), idem_key="k-1"
    )
    assert first.record_id == second.record_id

    records = app.records.list_records(scenario.uid("owner"), scenario.ledger_id)
    assert len(records) == 1
    create_logs = app.logs.count(
        scenario.uid("owner"), scenario.ledger_id, action=LogAction.CREATE_RECORD
    )
    assert create_logs == 1


def test_different_keys_create_two_records(scenario, app, payload) -> None:
    """不同幂等键代表两次独立提交。"""
    app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload(), idem_key="k-1"
    )
    app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload(), idem_key="k-2"
    )
    records = app.records.list_records(scenario.uid("owner"), scenario.ledger_id)
    assert len(records) == 2


def test_same_key_with_different_payload_rejected(scenario, app, payload) -> None:
    """同一幂等键用于不同内容时直接拒绝，避免静默串号。"""
    app.records.create_record(
        scenario.uid("member"), scenario.ledger_id, payload(amount="10"), idem_key="k-1"
    )
    with pytest.raises(ValidationError):
        app.records.create_record(
            scenario.uid("member"),
            scenario.ledger_id,
            payload(amount="20"),
            idem_key="k-1",
        )


def test_concurrent_approve_only_one_wins(scenario, app, make_record) -> None:
    """两个管理员同时审核同一条记录，只有一个成功（REQ-017）。"""
    record = make_record("member")
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker(user: str) -> None:
        try:
            barrier.wait(timeout=5)
            app.review.approve(scenario.uid(user), record.record_id)
            results.append("ok")
        except LedgerError as exc:  # 期望其中一个收到状态冲突
            results.append(exc.code)

    threads = [
        threading.Thread(target=worker, args=("admin",)),
        threading.Thread(target=worker, args=("owner",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert results.count("ok") == 1
    assert len(results) == 2
    view = app.records.get_record(scenario.uid("owner"), record.record_id)
    assert view.record.status is RecordStatus.APPROVED
    assert view.record.version == 2


def test_concurrent_create_with_same_key_creates_one_record(
    scenario, app, payload
) -> None:
    """并发重复提交同一请求也只落一条记录（REQ-016、REQ-017）。"""
    ids: list[str] = []
    barrier = threading.Barrier(3)

    def worker() -> None:
        barrier.wait(timeout=5)
        record = app.records.create_record(
            scenario.uid("member"),
            scenario.ledger_id,
            payload(amount="9.9"),
            idem_key="same-key",
        )
        ids.append(record.record_id)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(set(ids)) == 1
    records = app.records.list_records(scenario.uid("owner"), scenario.ledger_id)
    assert len(records) == 1
    create_logs = app.logs.count(
        scenario.uid("owner"), scenario.ledger_id, action=LogAction.CREATE_RECORD
    )
    assert create_logs == 1


def test_file_database_supports_multiple_connections(tmp_path) -> None:
    """文件数据库下多个连接看到同一份数据（并发测试的前提）。"""
    path = tmp_path / "ledger.db"
    first = Database(str(path))
    second = Database(str(path))
    try:
        first.connection().execute(
            "INSERT INTO users (user_id, username, display_name, password_hash, salt,"
            " created_at) VALUES ('u1', 'alice', 'Alice', 'h', 's', '2026-01-01T00:00:00')"
        )
        row = second.connection().execute(
            "SELECT username FROM users WHERE user_id = 'u1'"
        ).fetchone()
        assert row["username"] == "alice"
    finally:
        first.close()
        second.close()
