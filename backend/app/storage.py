"""SQLite 存储层共用配置。

所有 store 共享同一个数据库文件且每次操作新建连接：统一的 PRAGMA
配置保证写并发下的行为一致——

- ``journal_mode=WAL``：读写不再互相阻塞整库（rollback journal 下
  一次 Run 期间 trace / evidence / checkpoint / 审批的并发写会频繁
  争抢写锁）；
- ``busy_timeout=5000``：瞬时锁竞争等待而不是立刻抛
  "database is locked"。
"""

from __future__ import annotations

import aiosqlite

BUSY_TIMEOUT_MS = 5_000


async def configure_sqlite_connection(database: aiosqlite.Connection) -> None:
    """对单个连接应用共享 PRAGMA（幂等，开销微秒级）。"""

    await database.execute("PRAGMA journal_mode=WAL")
    await database.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")


__all__ = ["configure_sqlite_connection"]