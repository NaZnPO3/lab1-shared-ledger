"""结算测试（REQ-014、REQ-021、REQ-025）。"""

from __future__ import annotations

import pytest

from ledgershare.enums import LogAction, PeriodStatus, RecordStatus, TxnType
from ledgershare.errors import PermissionDenied, SettlementError, StateConflict


def test_settlement_math(scenario, app, make_record) -> None:
    """支出按在册成员均摊，成员余额相加为零（REQ-014）。"""
    first = make_record("member", amount="100")
    second = make_record("admin", amount="50")
    app.review.approve(scenario.uid("owner"), first.record_id)
    app.review.approve(scenario.uid("owner"), second.record_id)

    summary = app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)
    assert summary.total_expense_cents == 15_000

    balances = {line.member_id: line.balance_cents for line in summary.lines}
    assert len(balances) == 4
    assert sum(balances.values()) == 0
    # 每人应摊 37.5 元；成员甲垫付 100 元，管理员垫付 50 元
    assert sorted(balances.values()) == [-3_750, -3_750, 1_250, 6_250]
    assert all(line.paid_cents - line.share_cents == line.balance_cents for line in summary.lines)


def test_rounding_with_three_members(scenario, app, make_record) -> None:
    """除不尽的余数按成员顺序补 1 分，分摊合计仍等于支出合计。"""
    app.ledgers.leave_ledger(scenario.uid("readonly"), scenario.ledger_id)
    record = make_record("member", amount="100")
    app.review.approve(scenario.uid("owner"), record.record_id)

    summary = app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)
    shares = sorted(line.share_cents for line in summary.lines)
    assert shares == [3_333, 3_333, 3_334]
    assert sum(shares) == 10_000


def test_income_is_not_shared(scenario, app, make_record) -> None:
    """收入归记录人个人，不参与分摊。"""
    expense = make_record("member", amount="60")
    income = make_record("admin", amount="600", txn_type=TxnType.INCOME, category="工资")
    app.review.approve(scenario.uid("owner"), expense.record_id)
    app.review.approve(scenario.uid("owner"), income.record_id)

    summary = app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)
    assert summary.total_expense_cents == 6_000
    assert summary.total_income_cents == 60_000


def test_settlement_locks_period(scenario, app, make_record) -> None:
    """结算后该周期记录只能查，不能再改（REQ-025）。"""
    record = make_record("member", amount="30")
    app.review.approve(scenario.uid("admin"), record.record_id)
    summary = app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)

    assert summary.period.status is PeriodStatus.SETTLED
    assert summary.period.end_date is not None

    with pytest.raises(StateConflict):
        app.records.withdraw_record(scenario.uid("member"), record.record_id)
    with pytest.raises(StateConflict):
        app.review.void(scenario.uid("admin"), record.record_id)

    current = app.ledgers.current_period(scenario.uid("owner"), scenario.ledger_id)
    assert current.seq == 2
    assert current.is_open


def test_new_period_accepts_new_records(scenario, app, make_record) -> None:
    """结算只关闭当前周期，账本仍可继续记账（REQ-025）。"""
    record = make_record("member", amount="30")
    app.review.approve(scenario.uid("admin"), record.record_id)
    app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)

    fresh = make_record("member", amount="12")
    assert fresh.status is RecordStatus.PENDING
    current = app.ledgers.current_period(scenario.uid("owner"), scenario.ledger_id)
    assert fresh.period_id == current.period_id


def test_settlement_blocked_by_pending_records(scenario, app, make_record) -> None:
    """存在待审核记录时结算失败，并写入失败日志（REQ-021）。"""
    approved = make_record("member", amount="10")
    app.review.approve(scenario.uid("admin"), approved.record_id)
    make_record("member", amount="20")

    with pytest.raises(SettlementError):
        app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)

    failed = app.logs.count(
        scenario.uid("owner"), scenario.ledger_id, action=LogAction.SETTLE_FAILED
    )
    assert failed == 1
    assert app.ledgers.current_period(scenario.uid("owner"), scenario.ledger_id).is_open


def test_settlement_requires_approved_records(scenario, app, make_record) -> None:
    """没有已审核支出时结算失败。"""
    make_record("member", amount="10")
    with pytest.raises(SettlementError):
        app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)


def test_member_cannot_settle(scenario, app, make_record) -> None:
    """普通成员没有结算权限。"""
    record = make_record("member", amount="10")
    app.review.approve(scenario.uid("admin"), record.record_id)
    with pytest.raises(PermissionDenied):
        app.settlements.settle(scenario.uid("member"), scenario.ledger_id)


def test_settlement_preview_does_not_write(scenario, app, make_record) -> None:
    """预览结算不写任何数据。"""
    record = make_record("member", amount="10")
    app.review.approve(scenario.uid("admin"), record.record_id)
    preview = app.settlements.preview(scenario.uid("admin"), scenario.ledger_id)
    assert preview.total_expense_cents == 1_000

    period = app.ledgers.current_period(scenario.uid("owner"), scenario.ledger_id)
    assert period.is_open
    assert app.settlements.list_settlements(scenario.uid("owner"), period.period_id) == []


def test_settlement_history_is_queryable(scenario, app, make_record) -> None:
    """结算结果可以按周期查询。"""
    record = make_record("member", amount="40")
    app.review.approve(scenario.uid("admin"), record.record_id)
    summary = app.settlements.settle(scenario.uid("admin"), scenario.ledger_id)

    lines = app.settlements.list_settlements(
        scenario.uid("owner"), summary.period.period_id
    )
    assert len(lines) == 4
    assert sum(line.balance_cents for line in lines) == 0

    periods = app.settlements.list_periods(scenario.uid("owner"), scenario.ledger_id)
    assert len(periods) == 2
