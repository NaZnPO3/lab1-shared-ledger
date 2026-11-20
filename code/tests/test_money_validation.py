"""金额换算与输入校验的单元测试。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ledgershare.domain.validation import (
    RecordInput,
    parse_date_text,
    validate_amount,
    validate_ledger_name,
    validate_password,
    validate_record_input,
    validate_username,
)
from ledgershare.errors import ValidationError
from ledgershare.money import (
    format_cents,
    format_cents_signed,
    parse_amount,
)


def test_parse_amount_from_yuan() -> None:
    """整数与一位小数都能正确换算成分。"""
    assert parse_amount("1234") == 123_400
    assert parse_amount("1234.5") == 123_450
    assert parse_amount("0.01") == 1


def test_parse_amount_rejects_too_many_decimals() -> None:
    """超过两位小数应当被拒绝，避免四舍五入带来的金额误差。"""
    with pytest.raises(ValidationError):
        parse_amount("1.234")


def test_parse_amount_rejects_non_numeric() -> None:
    """非数字输入应当被拒绝。"""
    with pytest.raises(ValidationError):
        parse_amount("一百")


def test_format_cents() -> None:
    """金额格式化包含千分位与两位小数。"""
    assert format_cents(123_456) == "1,234.56"
    assert format_cents(0) == "0.00"
    assert format_cents(-5) == "-0.05"
    assert format_cents_signed(100) == "+1.00"


def test_validate_amount_bounds() -> None:
    """零、负数、超过上限的金额都被拒绝（REQ-015）。"""
    limit = 1_000_000
    assert validate_amount("1", limit) == 100
    with pytest.raises(ValidationError):
        validate_amount("0", limit)
    with pytest.raises(ValidationError):
        validate_amount("-1", limit)
    with pytest.raises(ValidationError):
        validate_amount("10001", limit)


def test_parse_date_text() -> None:
    """日期解析成功与失败两条路径。"""
    assert parse_date_text("2026-01-02") == date(2026, 1, 2)
    with pytest.raises(ValidationError):
        parse_date_text("")


def test_validate_credentials() -> None:
    """账号与密码的长度校验。"""
    assert validate_username("alice_01") == "alice_01"
    with pytest.raises(ValidationError):
        validate_username("ab")
    with pytest.raises(ValidationError):
        validate_username("bad name")
    assert validate_password("secret123") == "secret123"
    with pytest.raises(ValidationError):
        validate_password("123")


def test_validate_ledger_name_allows_duplicates_but_requires_text() -> None:
    """账本名可以为空以外的任意文本，重名由 ID 区分。"""
    assert validate_ledger_name("家庭账本") == "家庭账本"
    with pytest.raises(ValidationError):
        validate_ledger_name("   ")


def test_validate_record_input_accepts_valid_payload(scenario) -> None:
    """完整合法的记录应当通过校验。"""
    categories = {item.category_id: item for item in scenario.categories()}
    payload = RecordInput(
        amount="88.8",
        txn_type="expense",
        category_id=scenario.category_id("餐饮"),
        occurred_on=date.today().isoformat(),
        note="午饭",
    )
    validated = validate_record_input(
        payload,
        amount_limit_cents=1_000_000,
        categories=categories,
        earliest_date=date.today(),
        latest_date=date.today(),
    )
    assert validated.amount_cents == 8_880
    assert validated.note == "午饭"


def test_validate_record_input_rejects_category_type_mismatch(scenario) -> None:
    """支出记录不能使用收入分类。"""
    categories = {item.category_id: item for item in scenario.categories()}
    payload = RecordInput(
        amount="10",
        txn_type="income",
        category_id=scenario.category_id("餐饮"),
        occurred_on=date.today().isoformat(),
    )
    with pytest.raises(ValidationError):
        validate_record_input(
            payload,
            amount_limit_cents=1_000_000,
            categories=categories,
            earliest_date=date.today(),
        )


def test_validate_record_input_rejects_future_and_too_early_dates(scenario) -> None:
    """发生日期不能晚于今天，也不能早于当前周期起始日。"""
    categories = {item.category_id: item for item in scenario.categories()}
    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError):
        validate_record_input(
            RecordInput(
                amount="10",
                txn_type="expense",
                category_id=scenario.category_id("餐饮"),
                occurred_on=future,
            ),
            amount_limit_cents=1_000_000,
            categories=categories,
            latest_date=date.today(),
        )

    past = (date.today() - timedelta(days=3)).isoformat()
    with pytest.raises(ValidationError):
        validate_record_input(
            RecordInput(
                amount="10",
                txn_type="expense",
                category_id=scenario.category_id("餐饮"),
                occurred_on=past,
            ),
            amount_limit_cents=1_000_000,
            categories=categories,
            earliest_date=date.today(),
        )


def test_validate_record_input_rejects_long_note(scenario) -> None:
    """备注长度受限。"""
    categories = {item.category_id: item for item in scenario.categories()}
    payload = RecordInput(
        amount="10",
        txn_type="expense",
        category_id=scenario.category_id("餐饮"),
        occurred_on=date.today().isoformat(),
        note="备" * 201,
    )
    with pytest.raises(ValidationError):
        validate_record_input(
            payload,
            amount_limit_cents=1_000_000,
            categories=categories,
        )
