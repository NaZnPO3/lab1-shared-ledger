"""应用上下文：把数据库与各服务装配在一起。

界面层只需要持有 :class:`AppContext`，通过 ``app.records``、``app.review`` 等
属性调用业务能力，不直接接触 SQL。
"""

from __future__ import annotations

from pathlib import Path

from ..config import default_db_path
from ..data.database import Database
from ..models import User
from .auth_service import AuthService
from .ledger_service import LedgerService
from .log_service import LogService
from .record_service import RecordService
from .review_service import ReviewService
from .settlement_service import SettlementService
from .stats_service import LedgerOverview, StatsService, StatRow


class AppContext:
    """一次应用运行期间共享的服务容器。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db = Database(db_path or default_db_path())
        self.auth = AuthService(self.db)
        self.ledgers = LedgerService(self.db)
        self.records = RecordService(self.db)
        self.review = ReviewService(self.db)
        self.stats = StatsService(self.db)
        self.settlements = SettlementService(self.db)
        self.logs = LogService(self.db)
        self.current_user: User | None = None

    @property
    def db_location(self) -> str:
        """数据库文件位置，用于在界面上告知用户数据存放处。"""
        return str(self.db.path) if self.db.path else "内存数据库"

    def login(self, username: str, password: str) -> User:
        """登录并记住当前用户。"""
        user = self.auth.login(username, password)
        self.current_user = user
        return user

    def logout(self) -> None:
        """退出登录。"""
        self.current_user = None

    def close(self) -> None:
        """关闭数据库连接。"""
        self.db.close()


__all__ = [
    "AppContext",
    "LedgerOverview",
    "StatRow",
]
