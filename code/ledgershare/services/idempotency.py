"""幂等执行（REQ-016）。

界面在"提交"按钮按下时生成一个请求标识，同一次语义提交沿用同一个标识；
服务端先查幂等键，命中就直接返回第一次的结果，不再生成业务记录和日志。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Callable, Mapping

from ..data.database import Database
from ..data.repositories import IdempotencyRepository
from ..errors import ValidationError
from ..timeutil import now


def fingerprint(payload: Mapping[str, object]) -> str:
    """把请求内容折算成稳定摘要，用于识别"同标识不同内容"的误用。"""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class IdempotencyExecutor:
    """在单个写事务内完成"查幂等键 -> 执行 -> 记录键"。"""

    def __init__(self, db: Database) -> None:
        self._db = db

    def execute(
        self,
        *,
        user_id: str,
        key: str | None,
        action: str,
        request_hash: str,
        run: Callable[[sqlite3.Connection], str],
    ) -> tuple[str, bool]:
        """执行一次可能重复的写操作。

        Args:
            user_id: 发起请求的用户。
            key: 幂等键；为 ``None`` 时不做幂等处理。
            action: 操作名称，用于区分不同业务。
            request_hash: 请求内容摘要。
            run: 真正执行业务的回调，接收连接并返回业务对象 ID。

        Returns:
            ``(业务对象 ID, 是否为重复请求的复用结果)``。

        Raises:
            ValidationError: 同一幂等键被用于不同请求内容时抛出。
        """
        if not key:
            with self._db.transaction() as conn:
                return run(conn), False

        with self._db.transaction() as conn:
            repository = IdempotencyRepository(conn)
            existing = repository.find(user_id, key)
            if existing is not None:
                if existing["request_hash"] != request_hash:
                    raise ValidationError("同一请求标识不能用于内容不同的两次提交")
                return existing["record_id"] or "", True

            object_id = run(conn)
            repository.save(
                user_id=user_id,
                idem_key=key,
                action=action,
                request_hash=request_hash,
                record_id=object_id,
                created_at=now(),
            )
            return object_id, False
