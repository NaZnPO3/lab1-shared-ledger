"""统计服务测试（REQ-013）。"""

from __future__ import annotations

from ledgershare.enums import TxnType


def test_overview_only_counts_approved(scenario, app, make_record) -> None:
    """统计只算已审核记录，待审核与已作废不计入（REQ-013）。"""
    approved = make_record("member", amount="100")
    make_record("member", amount="50")
    voided = make_record("member", amount="30")
    app.review.approve(scenario.uid("admin"), approved.record_id)
    app.review.approve(scenario.uid("admin"), voided.record_id)
    app.review.void(scenario.uid("admin"), voided.record_id, "重复")

    overview = app.stats.overview(scenario.uid("owner"), scenario.ledger_id)
    assert overview.expense_cents == 10_000
    assert overview.income_cents == 0
    assert overview.pending_count == 1
    assert overview.record_count == 1


def test_income_overview(scenario, app, make_record) -> None:
    """收入与支出分别汇总。"""
    income = make_record("admin", amount="8000", txn_type=TxnType.INCOME, category="工资")
    expense = make_record("member", amount="120", category="购物")
    app.review.approve(scenario.uid("owner"), income.record_id)
    app.review.approve(scenario.uid("owner"), expense.record_id)

    overview = app.stats.overview(scenario.uid("owner"), scenario.ledger_id)
    assert overview.income_cents == 800_000
    assert overview.expense_cents == 12_000
    assert overview.net_cents == 788_000


def test_category_and_member_stats(scenario, app, make_record) -> None:
    """按分类、按成员统计的金额与条数正确。"""
    first = make_record("member", amount="40", category="餐饮")
    second = make_record("member", amount="60", category="餐饮")
    third = make_record("admin", amount="100", category="交通")
    for record in (first, second, third):
        app.review.approve(scenario.uid("owner"), record.record_id)

    by_category = app.stats.category_stats(scenario.uid("owner"), scenario.ledger_id)
    amounts = {row.group_name: row.amount_cents for row in by_category}
    assert amounts["餐饮"] == 10_000
    assert amounts["交通"] == 10_000
    counts = {row.group_name: row.count for row in by_category}
    assert counts["餐饮"] == 2

    by_member = app.stats.member_stats(scenario.uid("owner"), scenario.ledger_id)
    member_amounts = {row.group_name: row.amount_cents for row in by_member}
    assert member_amounts["成员甲"] == 10_000
    assert member_amounts["管理员"] == 10_000
