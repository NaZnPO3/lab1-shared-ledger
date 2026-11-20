"""收支记录服务测试（REQ-005、REQ-006、REQ-007、REQ-011、REQ-015、REQ-025）。"""

from __future__ import annotations

from datetime import date

import pytest

from ledgershare.enums import RecordStatus, TxnType
from ledgershare.errors import PermissionDenied, StateConflict, ValidationError


def test_create_record_starts_pending(make_record) -> None:
    """新记录状态为待审核，版本号为 1（REQ-005）。"""
    record = make_record("member", amount="23.45", note="午饭")
    assert record.status is RecordStatus.PENDING
    assert record.amount_cents == 2_345
    assert record.version == 1
    assert record.note == "午饭"


def test_readonly_cannot_create(make_record) -> None:
    """只读成员不能新增记录（REQ-003）。"""
    with pytest.raises(PermissionDenied):
        make_record("readonly", amount="10")


def test_amount_validation(make_record) -> None:
    """零、负数、超过上限的金额都被拒绝（REQ-015）。"""
    for amount in ("0", "-5", "1000000001"):
        with pytest.raises(ValidationError):
            make_record("member", amount=amount)


def test_withdraw_pending_record(scenario, app, make_record) -> None:
    """原记录人可以撤回待审核记录（REQ-006）。"""
    record = make_record("member")
    withdrawn = app.records.withdraw_record(scenario.uid("member"), record.record_id)
    assert withdrawn.status is RecordStatus.WITHDRAWN


def test_cannot_withdraw_others_record(scenario, app, make_record) -> None:
    """不能撤回别人提交的记录（REQ-006）。"""
    record = make_record("member")
    with pytest.raises(PermissionDenied):
        app.records.withdraw_record(scenario.uid("admin"), record.record_id)


def test_cannot_withdraw_approved_record(scenario, app, make_record) -> None:
    """已审核记录不能撤回，状态冲突（REQ-017）。"""
    record = make_record("member")
    app.review.approve(scenario.uid("admin"), record.record_id)
    with pytest.raises(StateConflict):
        app.records.withdraw_record(scenario.uid("member"), record.record_id)


def test_edit_rejected_record_resubmits(scenario, app, make_record, payload) -> None:
    """被驳回的记录可以修改并重新提交为待审核（REQ-007）。"""
    record = make_record("member", amount="10")
    app.review.reject(scenario.uid("admin"), record.record_id, "金额不对")
    edited = app.records.edit_rejected_record(
        scenario.uid("member"),
        record.record_id,
        payload(amount="12.5", note="改过了"),
    )
    assert edited.status is RecordStatus.PENDING
    assert edited.amount_cents == 1_250
    assert edited.note == "改过了"
    assert edited.version == 3


def test_cannot_edit_pending_record(scenario, app, make_record, payload) -> None:
    """待审核记录不能直接修改，只能撤回（REQ-007）。"""
    record = make_record("member")
    with pytest.raises(StateConflict):
        app.records.edit_rejected_record(
            scenario.uid("member"), record.record_id, payload(amount="99")
        )


def test_query_filters(scenario, app, make_record) -> None:
    """按状态、成员、类型、金额、关键词组合筛选（REQ-011）。"""
    first = make_record("member", amount="30", category="餐饮", note="早餐")
    second = make_record("member", amount="120", category="交通", note="打车")
    third = make_record(
        "admin", amount="5000", txn_type=TxnType.INCOME, category="工资", note="发工资"
    )
    app.review.approve(scenario.uid("admin"), first.record_id)
    app.review.approve(scenario.uid("admin"), third.record_id)

    pending = app.records.list_records(
        scenario.uid("owner"), scenario.ledger_id, statuses=[RecordStatus.PENDING]
    )
    assert [view.record.record_id for view in pending] == [second.record_id]

    expenses = app.records.list_records(
        scenario.uid("owner"), scenario.ledger_id, txn_type=TxnType.EXPENSE
    )
    assert {view.record.record_id for view in expenses} == {first.record_id, second.record_id}

    cheap = app.records.list_records(
        scenario.uid("owner"), scenario.ledger_id, amount_max_cents=5_000
    )
    assert {view.record.record_id for view in cheap} == {first.record_id}

    by_keyword = app.records.list_records(
        scenario.uid("owner"), scenario.ledger_id, keyword="打车"
    )
    assert len(by_keyword) == 1
    assert by_keyword[0].record.record_id == second.record_id

    by_date = app.records.list_records(
        scenario.uid("owner"),
        scenario.ledger_id,
        date_from=date.today(),
        date_to=date.today(),
    )
    assert len(by_date) == 3


def test_status_counts(scenario, app, make_record) -> None:
    """状态统计用于界面角标。"""
    make_record("member")
    make_record("member")
    counts = app.records.status_counts(scenario.uid("owner"), scenario.ledger_id)
    assert counts[RecordStatus.PENDING.value] == 2


def test_record_view_contains_names(scenario, app, make_record) -> None:
    """联表视图带出记录人与分类名称。"""
    record = make_record("member")
    view = app.records.get_record(scenario.uid("owner"), record.record_id)
    assert view.member_name == "成员甲"
    assert view.category_name == "餐饮"
