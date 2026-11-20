"""时间工具。

本程序是单机桌面应用，所有时间统一按本机本地时间保存为不带时区的 ISO 字符串，
省去跨时区换算，方便直接阅读数据库内容。
"""

from __future__ import annotations

from datetime import date, datetime

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"


def now() -> datetime:
    """返回当前本地时间（精确到秒）。"""
    return datetime.now().replace(microsecond=0)


def today() -> date:
    """返回今天的日期。"""
    return date.today()


def to_text(moment: datetime) -> str:
    """把时间格式化为数据库存储用的字符串。"""
    return moment.replace(microsecond=0).strftime(DATETIME_FORMAT)


def to_date_text(moment: date) -> str:
    """把日期格式化为数据库存储用的字符串。"""
    return moment.strftime(DATE_FORMAT)


def parse_datetime(text: str | None) -> datetime | None:
    """把数据库中的时间字符串解析为 :class:`datetime`。"""
    if not text:
        return None
    return datetime.fromisoformat(text)


def parse_date(text: str | None) -> date | None:
    """把数据库中的日期字符串解析为 :class:`date`。"""
    if not text:
        return None
    return date.fromisoformat(text)
