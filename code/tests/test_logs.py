"""操作日志测试（REQ-018、REQ-020）。"""

from __future__ import annotations

import pytest

from ledgershare.enums import LogAction, LogResult
from ledgershare.errors import PermissionDenied


def test_create_record_writes_log(scenario, app, make_record) -> None:
    """新增记录留下一条成功日志。"""
    make_record("member")
    entries = app.logs.list_for_ledger(scenario.uid("owner"), scenario.ledger_id)
    create_entries = [item for item in entries if item.action == LogAction.CREATE_RECORD.value]
    assert len(create_entries) == 1
    assert create_entries[0].result == LogResult.SUCCESS.value
    assert create_entries[0].actor_user_id == scenario.uid("member")


def test_unauthorized_attempt_is_logged(scenario, app, payload) -> None:
    """越权请求被拒绝，但会留下一条"已拒绝"日志（REQ-020）。"""
    with pytest.raises(PermissionDenied):
        app.records.create_record(scenario.uid("readonly"), scenario.ledger_id, payload())

    entries = app.logs.list_for_ledger(scenario.uid("owner"), scenario.ledger_id)
    denied = [item for item in entries if item.action == LogAction.UNAUTHORIZED.value]
    assert len(denied) == 1
    assert denied[0].result == LogResult.DENIED.value
    assert denied[0].actor_user_id == scenario.uid("readonly")


def test_only_admin_can_read_logs(scenario, app) -> None:
    """普通成员不能查询操作日志。"""
    with pytest.raises(PermissionDenied):
        app.logs.list_for_ledger(scenario.uid("member"), scenario.ledger_id)
    entries = app.logs.list_for_ledger(scenario.uid("admin"), scenario.ledger_id)
    assert entries


def test_review_and_void_are_logged(scenario, app, make_record) -> None:
    """审核与作废都留痕，且记录处理结果。"""
    record = make_record("member")
    app.review.approve(scenario.uid("admin"), record.record_id)
    app.review.void(scenario.uid("admin"), record.record_id, "测试")

    actions = {
        item.action
        for item in app.logs.list_for_ledger(scenario.uid("owner"), scenario.ledger_id)
    }
    assert LogAction.APPROVE_RECORD.value in actions
    assert LogAction.VOID_RECORD.value in actions
