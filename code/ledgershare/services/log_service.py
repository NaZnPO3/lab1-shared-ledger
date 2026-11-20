"""操作日志查询服务（REQ-018、REQ-022）。

日志只追加不修改；管理员与创建者可以查询本账本的日志，
用于核对审核、作废、越权与结算失败等关键动作。
"""

from __future__ import annotations

from ..enums import LogAction, Permission
from ..models import OperationLogEntry
from .base import BaseService


class LogService(BaseService):
    """操作日志的查询入口。"""

    def list_for_ledger(
        self, actor_user_id: str, ledger_id: str, limit: int = 200
    ) -> list[OperationLogEntry]:
        """列出账本最近的操作日志。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_LOGS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.logs(conn).list_by_ledger(ledger_id, limit=limit)

    def count(
        self,
        actor_user_id: str,
        ledger_id: str,
        *,
        action: LogAction | None = None,
    ) -> int:
        """统计日志条数，主要用于验证"重复请求不产生重复日志"（REQ-016）。"""
        self.authorize(
            ledger_id=ledger_id,
            user_id=actor_user_id,
            permission=Permission.VIEW_LOGS,
            action=LogAction.CREATE_RECORD,
            target_type="ledger",
            target_id=ledger_id,
        )
        with self.db.reading() as conn:
            return self.logs(conn).count(
                ledger_id=ledger_id, action=action.value if action else None
            )
