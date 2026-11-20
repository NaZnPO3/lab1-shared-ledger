"""输入校验（REQ-005、REQ-015）。

校验放在领域层，界面和服务层共用同一份规则，避免"界面上校验过、接口没过"的漏洞。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..config import PASSWORD_MIN_LENGTH
from ..enums import TxnType
from ..errors import ValidationError
from ..models import Category
from ..money import parse_amount

MAX_NOTE_LENGTH = 200
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 20


@dataclass(frozen=True, slots=True)
class RecordInput:
    """界面提交上来的原始记录数据（尚未校验）。"""

    amount: str
    txn_type: str
    category_id: str
    occurred_on: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class ValidatedRecord:
    """通过校验、可直接写入数据库的记录数据。"""

    amount_cents: int
    txn_type: TxnType
    category_id: str
    occurred_on: date
    note: str


def parse_txn_type(value: str | TxnType) -> TxnType:
    """把字符串转换为收支类型。

    Raises:
        ValidationError: 取值既不是收入也不是支出时抛出。
    """
    if isinstance(value, TxnType):
        return value
    try:
        return TxnType(value)
    except ValueError as exc:
        raise ValidationError("收支类型只能是收入或支出") from exc


def parse_date_text(value: str | date) -> date:
    """解析 ``YYYY-MM-DD`` 形式的日期。

    Raises:
        ValidationError: 日期为空或格式错误时抛出。
    """
    if isinstance(value, date):
        return value
    text = (value or "").strip()
    if not text:
        raise ValidationError("请填写发生日期")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("发生日期格式应为 YYYY-MM-DD") from exc


def validate_amount(amount: str, amount_limit_cents: int) -> int:
    """校验金额：必须大于 0 且不超过账本上限（REQ-015）。

    Raises:
        ValidationError: 金额非法时抛出。
    """
    cents = parse_amount(amount)
    if cents <= 0:
        raise ValidationError("金额必须大于 0")
    if cents > amount_limit_cents:
        raise ValidationError("金额超过账本上限，请修改账本设置")
    return cents


def validate_record_input(
    payload: RecordInput,
    *,
    amount_limit_cents: int,
    categories: dict[str, Category],
    earliest_date: date | None = None,
    latest_date: date | None = None,
) -> ValidatedRecord:
    """校验一条新增或修改后的收支记录。

    Args:
        payload: 界面提交的原始数据。
        amount_limit_cents: 账本配置的金额上限。
        categories: 该账本可用的分类，键为分类 ID。
        earliest_date: 允许的最早发生日期（当前结算周期起始日）。
        latest_date: 允许的最晚发生日期（一般为今天）。

    Returns:
        校验通过的数据。

    Raises:
        ValidationError: 任一字段不合法时抛出。
    """
    txn_type = parse_txn_type(payload.txn_type)
    amount_cents = validate_amount(payload.amount, amount_limit_cents)

    category = categories.get(payload.category_id)
    if category is None:
        raise ValidationError("请选择有效的分类")
    if category.applies_to is not txn_type:
        raise ValidationError(
            f"分类“{category.name}”只适用于{category.applies_to.label}"
        )

    occurred_on = parse_date_text(payload.occurred_on)
    if earliest_date is not None and occurred_on < earliest_date:
        raise ValidationError(
            f"发生日期不能早于当前结算周期起始日 {earliest_date.isoformat()}"
        )
    if latest_date is not None and occurred_on > latest_date:
        raise ValidationError("发生日期不能晚于今天")

    note = (payload.note or "").strip()
    if len(note) > MAX_NOTE_LENGTH:
        raise ValidationError(f"备注不能超过 {MAX_NOTE_LENGTH} 个字符")

    return ValidatedRecord(
        amount_cents=amount_cents,
        txn_type=txn_type,
        category_id=category.category_id,
        occurred_on=occurred_on,
        note=note,
    )


def validate_username(username: str) -> str:
    """校验账号：长度 3~20，仅允许字母、数字、下划线和减号。

    Raises:
        ValidationError: 账号不合法时抛出。
    """
    text = (username or "").strip()
    if not MIN_USERNAME_LENGTH <= len(text) <= MAX_USERNAME_LENGTH:
        raise ValidationError(
            f"账号长度应为 {MIN_USERNAME_LENGTH}~{MAX_USERNAME_LENGTH} 个字符"
        )
    if not all(char.isalnum() or char in "_-" for char in text):
        raise ValidationError("账号只能包含字母、数字、下划线和减号")
    return text


def validate_password(password: str) -> str:
    """校验密码长度。

    Raises:
        ValidationError: 密码太短时抛出。
    """
    if len(password or "") < PASSWORD_MIN_LENGTH:
        raise ValidationError(f"密码至少 {PASSWORD_MIN_LENGTH} 位")
    return password


def validate_display_name(name: str) -> str:
    """校验昵称，为空时回退为账号。

    Raises:
        ValidationError: 昵称过长时抛出。
    """
    text = (name or "").strip()
    if len(text) > MAX_USERNAME_LENGTH:
        raise ValidationError(f"昵称不能超过 {MAX_USERNAME_LENGTH} 个字符")
    return text


def validate_ledger_name(name: str) -> str:
    """校验账本名称，同名账本允许存在（REQ-001）。

    Raises:
        ValidationError: 名称为空或过长时抛出。
    """
    text = (name or "").strip()
    if not text:
        raise ValidationError("请填写账本名称")
    if len(text) > 30:
        raise ValidationError("账本名称不能超过 30 个字符")
    return text
