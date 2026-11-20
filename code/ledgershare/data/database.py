"""SQLite 连接与事务管理。

设计要点：

* 每个线程各自持有一个连接（``threading.local``），配合 WAL 与
  ``BEGIN IMMEDIATE`` 让并发写入串行化，满足 REQ-017 对并发一致性的要求；
* 事务支持保存点，服务内部可以安全嵌套调用；
* 内存数据库使用共享缓存 URI，多个线程仍访问同一个库。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from itertools import count
from pathlib import Path
from typing import Iterator, Sequence

from .schema import SCHEMA_SQL

MEMORY_DSN_PREFIX = "file:ledger_mem_"


class Database:
    """封装数据库连接、初始化与事务边界。"""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._counter = count(1)
        self._local = threading.local()
        self._anchor: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            self._dsn = f"{MEMORY_DSN_PREFIX}{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._use_uri = True
            self.path: Path | None = None
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._dsn = str(self.path)
            self._use_uri = False
        self._initialize()

    # ------------------------------------------------------------------ 连接
    def connection(self) -> sqlite3.Connection:
        """返回当前线程的连接，必要时新建并完成初始化。"""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(
            self._dsn,
            uri=self._use_uri,
            isolation_level=None,
            timeout=15.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        if not self._use_uri:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        self._local.conn = conn
        if self._anchor is None:
            self._anchor = conn
        return conn

    def _initialize(self) -> None:
        """建表；已存在时不做任何破坏性操作。"""
        conn = self.connection()
        conn.executescript(SCHEMA_SQL)

    # ------------------------------------------------------------------ 事务
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """开启一个写事务；嵌套调用时自动降级为保存点。"""
        conn = self.connection()
        if conn.in_transaction:
            name = f"sp_{next(self._counter)}"
            conn.execute(f"SAVEPOINT {name}")
            try:
                yield conn
            except Exception:  # noqa: BLE001 - 需要无条件回滚
                conn.execute(f"ROLLBACK TO {name}")
                conn.execute(f"RELEASE {name}")
                raise
            conn.execute(f"RELEASE {name}")
            return

        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:  # noqa: BLE001 - 需要无条件回滚
            conn.rollback()
            raise
        conn.commit()

    @contextmanager
    def reading(self) -> Iterator[sqlite3.Connection]:
        """只读查询的连接上下文，失败时不做特殊处理。"""
        yield self.connection()

    # ------------------------------------------------------------------ 便捷
    def fetch_all(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[sqlite3.Row]:
        """执行查询并返回全部结果。"""
        return list(self.connection().execute(sql, params).fetchall())

    def fetch_one(
        self, sql: str, params: Sequence[object] = ()
    ) -> sqlite3.Row | None:
        """执行查询并返回第一条结果。"""
        return self.connection().execute(sql, params).fetchone()

    def close(self) -> None:
        """关闭当前线程连接与内存库锚点连接。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        if self._anchor is not None:
            self._anchor.close()
            self._anchor = None
