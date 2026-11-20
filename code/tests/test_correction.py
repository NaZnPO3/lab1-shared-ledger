"""更正流程测试（REQ-010）。"""

from __future__ import annotations

import pytest

from ledgershare.enums import RecordStatus
from ledgershare.errors import PermissionDenied, StateConflict


def test_correction_is_a_new_record(scenario, app, make_record, payload) -> None:
    """更正是指向原记录的新记录，原记录在审核通过前保持不变（REQ-010）。"""
    original = make_record("member", amount="100")
    app.review.approve(scenario.uid("admin"), original.record_id)

    correction = app.review.submit_correction(
        scenario.uid("member"),
        original.record_id,
        payload(amount="80", note="金额记错了"),
    )
    assert correction.status is RecordStatus.PENDING
    assert correction.corrects_record_id == original.record_id
    assert correction.amount_cents == 8_000

    still = app.records.get_record(scenario.uid("owner"), original.record_id)
    assert still.record.status is RecordStatus.APPROVED


def test_approving_correction_voids_original(scenario, app, make_record, payload) -> None:
    """更正通过后原记录作废，两条记录都保留（REQ-010）。"""
    original = make_record("member", amount="100")
    app.review.approve(scenario.uid("admin"), original.record_id)
    correction = app.review.submit_correction(
        scenario.uid("member"), original.record_id, payload(amount="80")
    )

    app.review.approve(scenario.uid("admin"), correction.record_id)

    original_view = app.records.get_record(scenario.uid("owner"), original.record_id)
    correction_view = app.records.get_record(scenario.uid("owner"), correction.record_id)
    assert original_view.record.status is RecordStatus.VOIDED
    assert correction_view.record.status is RecordStatus.APPROVED


def test_rejecting_correction_keeps_original(scenario, app, make_record, payload) -> None:
    """更正被驳回时原记录仍为已审核，不产生作废。"""
    original = make_record("member", amount="100")
    app.review.approve(scenario.uid("admin"), original.record_id)
    correction = app.review.submit_correction(
        scenario.uid("member"), original.record_id, payload(amount="80")
    )
    app.review.reject(scenario.uid("admin"), correction.record_id, "依据不足")

    original_view = app.records.get_record(scenario.uid("owner"), original.record_id)
    correction_view = app.records.get_record(scenario.uid("owner"), correction.record_id)
    assert original_view.record.status is RecordStatus.APPROVED
    assert correction_view.record.status is RecordStatus.REJECTED


def test_correction_requires_approved_original(scenario, app, make_record, payload) -> None:
    """待审核记录不能走更正流程（REQ-010）。"""
    record = make_record("member")
    with pytest.raises(StateConflict):
        app.review.submit_correction(
            scenario.uid("member"), record.record_id, payload(amount="1")
        )


def test_cannot_correct_others_record(scenario, app, make_record, payload) -> None:
    """只能对自己的记录提交更正。"""
    original = make_record("member", amount="100")
    app.review.approve(scenario.uid("admin"), original.record_id)
    with pytest.raises(PermissionDenied):
        app.review.submit_correction(
            scenario.uid("admin"), original.record_id, payload(amount="50")
        )
