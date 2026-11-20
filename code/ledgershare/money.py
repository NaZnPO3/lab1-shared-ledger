"""金额换算。

数据库统一以"分"为单位的整数保存金额，避免浮点误差；界面与报表使用
:func:`format_cents` 输出两位小数。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .errors import ValidationError

CENTS_PER_YUAN = 100
MAX_DECIMAL_PLACES = 2


def parse_amount(text: str | Decimal | int | float) -> int:
    """把用户输入的金额转换为整数分。

    Args:
        text: 用户输入的金额文本，或 Decimal/int/float 数值。

    Returns:
        以分为单位的金额。

    Raises:
        ValidationError: 输入不是合法数字，或小数位超过两位。
    """
    try:
        amount = Decimal(str(text).strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise ValidationError("金额必须是数字") from exc
    if not amount.is_finite():
        raise ValidationError("金额必须是数字")
    if -amount.as_tuple().exponent > MAX_DECIMAL_PLACES:
        raise ValidationError("金额最多保留两位小数")
    return int(amount.scaleb(MAX_DECIMAL_PLACES).to_integral_value())


def format_cents(cents: int) -> str:
    """把整数分格式化为带千分位的两位小数字符串。"""
    sign = "-" if cents < 0 else ""
    yuan, fen = divmod(abs(int(cents)), CENTS_PER_YUAN)
    return f"{sign}{yuan:,}.{fen:02d}"


def format_cents_signed(cents: int) -> str:
    """格式化金额，并显式给出正号，便于展示"应收"金额。"""
    return f"+{format_cents(cents)}" if cents > 0 else format_cents(cents)


def yuan_to_cents(yuan: str | Decimal | int | float) -> int:
    """:func:`parse_amount` 的语义别名，用于强调输入单位是元。"""
    return parse_amount(yuan)
