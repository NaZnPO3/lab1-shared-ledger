"""审核、驳回、作废测试（REQ-008、REQ-009、REQ-017、REQ-025）。"""

from __future__ import annotations

import pytest

from ledgershare.enums import RecordStatus
from ledgershare.errors import PermissionDenied, StateConflict


def test_approve_and_reject(scenario, app, make_record) -> None:
    """管理员可以审核通过或驳回待审核记录（REQ-008）。"""
    first = make_record("member")
    approved = app.review.approve(scenario.uid("admin"), first.record_id)
    assert approved.status is RecordStatus.APPROVED

    second = make_record("member")
    rejected = app.review.reject(scenario.uid("admin"), second.record_id, "票据缺失")
    assert rejected.status is RecordStatus.REJECTED


def test_member_cannot_review(scenario, app, make_record) -> None:
    """普通成员与只读成员没有审核权限（REQ-020）。"""
    record = make_record("member")
    for actor in ("member", "readonly"):
        with pytest.raises(PermissionDenied):
            app.review.approve(scenario.uid(actor), record.record_id)


def test_void_approved_record(scenario, app, make_record) -> None:
    """已审核记录可以作废，记录本身保留（REQ-009）。"""
    record = make_record("member")
    app.review.approve(scenario.uid("admin"), record.record_id)
    voided = app.review.void(scenario.uid("admin"), record.record_id, "重复记账")
    assert voided.status is RecordStatus.VOIDED
    view = app.records.get_record(scenario.uid("owner"), record.record_id)
    assert view.record.note is not None


def test_void_pending_record_conflicts(scenario, app, make_record) -> None:
    """待审核记录不能直接作废（REQ-009）。"""
    record = make_record("member")
    with pytest.raises(StateConflict):
        app.review.void(scenario.uid("admin"), record.record_id)


def test_double_approve_conflicts(scenario, app, make_record) -> None:
    """同一记录不能审核两次（REQ-017）。"""
    record = make_record("member")
    app.review.approve(scenario.uid("admin"), record.record_id)
    with pytest.raises(StateConflict):
        app.review.approve(scenario.uid("owner"), record.record_id)


def test_owner_can_review_too(scenario, app, make_record) -> None:
    """创建者同样具备审核权限。"""
    record = make_record("member")
    approved = app.review.approve(scenario.uid("owner"), record.record_id)
    assert approved.status is RecordStatus.APPROVED
