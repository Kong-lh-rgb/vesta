"""基于 SQLite 的不可变 Evidence Store。"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.conversation.store import DEFAULT_DATABASE_PATH

from .models import EvidenceDocument, EvidenceRecord, EvidenceSearchHit

logger = logging.getLogger("vesta.evidence.store")

# FTS5 trigram 投影：external-content 模式（content 表即 evidence，不复制原文），
# 由触发器保持同步；损坏或不可用时降级回 instr 子串扫描，原文不受影响。
_FTS_SCHEMA_VERSION = "1"
_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    content,
    tokenize = 'trigram',
    content = 'evidence',
    content_rowid = 'rowid'
);

CREATE TABLE IF NOT EXISTS evidence_fts_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS evidence_fts_ai AFTER INSERT ON evidence BEGIN
    INSERT INTO evidence_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS evidence_fts_ad AFTER DELETE ON evidence BEGIN
    INSERT INTO evidence_fts(evidence_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS evidence_fts_au AFTER UPDATE ON evidence BEGIN
    INSERT INTO evidence_fts(evidence_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
    INSERT INTO evidence_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_chars INTEGER NOT NULL,
    content_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    task_id TEXT,
    task_step_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, tool_call_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_conversation_created
ON evidence(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_conversation_task
ON evidence(conversation_id, task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_run
ON evidence(run_id, created_at ASC);
"""
_EVIDENCE_ID_RE = re.compile(r"^[0-9a-f]{4,32}$")
DEFAULT_MAX_EVIDENCE_ITEM_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_EVIDENCE_TOTAL_BYTES = 512 * 1024 * 1024


def _fts_phrase(query: str) -> str:
    """把自由文本查询转成安全的一个 FTS5 短语（语义等价于子串匹配）。"""

    escaped = query.replace('"', " ")
    return f'"{escaped}"'


class EvidenceCapacityError(ValueError):
    """Evidence 容量边界拒绝了新原文，已有证据保持不变。"""


class SQLiteEvidenceStore:
    """保存完整工具输出，并强制所有模型查询先按会话隔离。"""

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
        *,
        max_item_bytes: int = DEFAULT_MAX_EVIDENCE_ITEM_BYTES,
        max_total_bytes: int = DEFAULT_MAX_EVIDENCE_TOTAL_BYTES,
    ) -> None:
        if max_item_bytes < 1 or max_total_bytes < 1:
            raise ValueError("evidence capacity limits must be positive")
        if max_item_bytes > max_total_bytes:
            raise ValueError("max_item_bytes cannot exceed max_total_bytes")
        self.database_path = Path(database_path).expanduser().resolve()
        self.max_item_bytes = max_item_bytes
        self.max_total_bytes = max_total_bytes
        self._fts_ready = False

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as database:
            await database.executescript(_SCHEMA)
            await database.commit()
            await self._initialize_fts(database)

    async def _initialize_fts(self, database: aiosqlite.Connection) -> None:
        """建立 FTS 投影；首次（或结构版本变化）全量重建一次。

        FTS5 不可用或损坏只影响检索路径，不阻塞 Evidence 原文读写。
        """

        try:
            await database.executescript(_FTS_DDL)
            rows = await database.execute_fetchall(
                "SELECT value FROM evidence_fts_state WHERE key = 'schema_version'"
            )
            needs_rebuild = not rows or rows[0][0] != _FTS_SCHEMA_VERSION
            if not needs_rebuild:
                # 对账：投影行数与原文不一致（外部手工破坏 / 中断）时重建。
                # 静默不一致不会在检索时抛错，只能靠启动计数发现。
                evidence_count = await database.execute_fetchall(
                    "SELECT COUNT(*) FROM evidence"
                )
                fts_count = await database.execute_fetchall(
                    "SELECT COUNT(*) FROM evidence_fts"
                )
                needs_rebuild = evidence_count[0][0] != fts_count[0][0]
            if needs_rebuild:
                await database.execute(
                    "INSERT INTO evidence_fts(evidence_fts) VALUES ('rebuild')"
                )
                await database.execute(
                    "INSERT OR REPLACE INTO evidence_fts_state (key, value) "
                    "VALUES ('schema_version', ?)",
                    (_FTS_SCHEMA_VERSION,),
                )
            await database.commit()
            self._fts_ready = True
        except aiosqlite.Error as exc:
            await database.rollback()
            self._fts_ready = False
            logger.warning("evidence FTS projection unavailable: %s", exc)

    async def create(
        self,
        *,
        conversation_id: str,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        content: str,
        sha256: str,
        task_id: str | None = None,
        task_step_id: str | None = None,
    ) -> EvidenceRecord:
        """创建不可变证据；同一 Run/ToolCall 的相同内容幂等返回。"""

        conversation_id = _required(conversation_id, "conversation_id")
        run_id = _required(run_id, "run_id")
        tool_call_id = _required(tool_call_id, "tool_call_id")
        tool_name = _required(tool_name, "tool_name")
        evidence_id = uuid4().hex
        created_at = datetime.now(UTC)
        content_bytes = len(content.encode("utf-8"))
        async with self._connect() as database:
            try:
                # 串行化“幂等检查 + 容量检查 + 写入”，避免并发重放绕过限制。
                await database.execute("BEGIN IMMEDIATE")
                cursor = await database.execute(
                    "SELECT * FROM evidence WHERE run_id = ? AND tool_call_id = ?",
                    (run_id, tool_call_id),
                )
                existing = await cursor.fetchone()
                if existing is not None:
                    if (
                        existing["sha256"] != sha256
                        or existing["conversation_id"] != conversation_id
                        or existing["tool_name"] != tool_name
                    ):
                        raise ValueError(
                            "evidence conflict: tool call already has different facts"
                        )
                    await database.commit()
                    return _record_from_row(existing)
                if content_bytes > self.max_item_bytes:
                    raise EvidenceCapacityError(
                        "evidence item exceeds max_item_bytes: "
                        f"{content_bytes} > {self.max_item_bytes}"
                    )
                cursor = await database.execute(
                    "SELECT COALESCE(SUM(content_bytes), 0) AS total FROM evidence"
                )
                total_bytes = int((await cursor.fetchone())["total"])
                if total_bytes + content_bytes > self.max_total_bytes:
                    raise EvidenceCapacityError(
                        "evidence store exceeds max_total_bytes: "
                        f"{total_bytes + content_bytes} > {self.max_total_bytes}"
                    )
                await database.execute(
                    """
                    INSERT INTO evidence (
                        id, conversation_id, run_id, tool_call_id, tool_name,
                        content_type, content, content_chars, content_bytes, sha256,
                        task_id, task_step_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        conversation_id,
                        run_id,
                        tool_call_id,
                        tool_name,
                        "text/plain; charset=utf-8",
                        content,
                        len(content),
                        content_bytes,
                        sha256,
                        task_id,
                        task_step_id,
                        created_at.isoformat(),
                    ),
                )
                await database.commit()
            except Exception:
                await database.rollback()
                raise
        return EvidenceRecord(
            id=evidence_id,
            conversation_id=conversation_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content_chars=len(content),
            content_bytes=content_bytes,
            sha256=sha256,
            task_id=task_id,
            task_step_id=task_step_id,
            created_at=created_at,
        )

    async def resolve(
        self,
        identifier: str,
        *,
        conversation_id: str,
    ) -> EvidenceDocument | None:
        """在当前会话内按完整 ID 或唯一前缀读取证据。"""

        normalized = identifier.strip().lower()
        if not _EVIDENCE_ID_RE.fullmatch(normalized):
            raise ValueError(
                "evidence id must be a 4-32 character hexadecimal prefix"
            )
        async with self._connect() as database:
            cursor = await database.execute(
                """
                SELECT * FROM evidence
                WHERE conversation_id = ? AND id LIKE ?
                ORDER BY created_at DESC LIMIT 2
                """,
                (_required(conversation_id, "conversation_id"), f"{normalized}%"),
            )
            rows = await cursor.fetchall()
        if len(rows) > 1:
            raise ValueError(f"Evidence ID 前缀不唯一：{identifier}")
        if not rows:
            return None
        return EvidenceDocument(
            record=_record_from_row(rows[0]),
            content=rows[0]["content"],
        )

    async def search(
        self,
        *,
        conversation_id: str,
        query: str,
        tool_name: str | None = None,
        task_id: str | None = None,
        limit: int = 10,
    ) -> tuple[EvidenceSearchHit, ...]:
        """在当前会话内检索原始输出，返回有界片段而非整份内容。

        检索路径：FTS5 trigram 投影优先（避免全表扫描）；查询不足 3 个
        字符、投影不可用或损坏（自愈重建失败）时降级回 instr 子串扫描。
        两条路径都强制 conversation_id（及可选 tool/task）隔离，行为一致。
        """

        if limit < 1 or limit > 20:
            raise ValueError("limit must be between 1 and 20")
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must be a non-empty string")
        conversation_id = _required(conversation_id, "conversation_id")

        if self._fts_ready and len(normalized_query) >= 3:
            rows = await self._search_fts_rows(
                conversation_id=conversation_id,
                query=normalized_query,
                tool_name=tool_name,
                task_id=task_id,
                limit=limit,
            )
            if rows is not None:
                return self._hits_from_rows(rows, normalized_query)
        rows = await self._search_scan_rows(
            conversation_id=conversation_id,
            query=normalized_query,
            tool_name=tool_name,
            task_id=task_id,
            limit=limit,
        )
        return self._hits_from_rows(rows, normalized_query)

    def _hits_from_rows(
        self,
        rows,
        normalized_query: str,
    ) -> tuple[EvidenceSearchHit, ...]:
        return tuple(
            EvidenceSearchHit(
                record=_record_from_row(row),
                snippet=_snippet(row["content"], normalized_query),
            )
            for row in rows
        )

    async def _search_fts_rows(
        self,
        *,
        conversation_id: str,
        query: str,
        tool_name: str | None,
        task_id: str | None,
        limit: int,
    ):
        """FTS 路径；投影异常时自愈重建一次，仍失败返回 None 走降级。"""

        sql, parameters = self._search_sql(
            fts=True,
            conversation_id=conversation_id,
            query=query,
            tool_name=tool_name,
            task_id=task_id,
            limit=limit,
        )
        try:
            async with self._connect() as database:
                cursor = await database.execute(sql, tuple(parameters))
                return await cursor.fetchall()
        except aiosqlite.Error as exc:
            logger.warning("evidence FTS search failed, rebuilding: %s", exc)
            try:
                async with self._connect() as database:
                    await database.execute(
                        "INSERT INTO evidence_fts(evidence_fts) VALUES ('rebuild')"
                    )
                    await database.commit()
                async with self._connect() as database:
                    cursor = await database.execute(sql, tuple(parameters))
                    return await cursor.fetchall()
            except aiosqlite.Error as fallback_exc:
                self._fts_ready = False
                logger.warning(
                    "evidence FTS rebuild failed, falling back to scan: %s",
                    fallback_exc,
                )
                return None

    async def _search_scan_rows(
        self,
        *,
        conversation_id: str,
        query: str,
        tool_name: str | None,
        task_id: str | None,
        limit: int,
    ):
        sql, parameters = self._search_sql(
            fts=False,
            conversation_id=conversation_id,
            query=query,
            tool_name=tool_name,
            task_id=task_id,
            limit=limit,
        )
        async with self._connect() as database:
            cursor = await database.execute(sql, tuple(parameters))
            return await cursor.fetchall()

    @staticmethod
    def _search_sql(
        *,
        fts: bool,
        conversation_id: str,
        query: str,
        tool_name: str | None,
        task_id: str | None,
        limit: int,
    ) -> tuple[str, list[object]]:
        if fts:
            base = (
                "SELECT e.* FROM evidence_fts AS f "
                "JOIN evidence AS e ON e.rowid = f.rowid "
                "WHERE evidence_fts MATCH ? AND e.conversation_id = ?"
            )
            parameters: list[object] = [_fts_phrase(query), conversation_id]
        else:
            base = (
                "SELECT * FROM evidence WHERE conversation_id = ? "
                "AND instr(lower(content), lower(?)) > 0"
            )
            parameters = [conversation_id, query]
        if tool_name:
            base += " AND tool_name = ?"
            parameters.append(tool_name.strip())
        if task_id:
            base += " AND task_id = ?"
            parameters.append(task_id.strip())
        base += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        return base, parameters

    async def list_recent(
        self,
        *,
        conversation_id: str,
        limit: int = 12,
    ) -> tuple[EvidenceRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        async with self._connect() as database:
            cursor = await database.execute(
                """
                SELECT * FROM evidence WHERE conversation_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (_required(conversation_id, "conversation_id"), limit),
            )
            rows = await cursor.fetchall()
        return tuple(_record_from_row(row) for row in rows)

    async def list_for_task(
        self,
        *,
        conversation_id: str,
        task_id: str,
        limit: int = 20,
    ) -> tuple[EvidenceRecord, ...]:
        async with self._connect() as database:
            cursor = await database.execute(
                """
                SELECT * FROM evidence
                WHERE conversation_id = ? AND task_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (
                    _required(conversation_id, "conversation_id"),
                    _required(task_id, "task_id"),
                    limit,
                ),
            )
            rows = await cursor.fetchall()
        return tuple(_record_from_row(row) for row in rows)

    async def delete_for_conversation(self, conversation_id: str) -> int:
        """删除某会话归档的全部工具原始证据。"""

        normalized = _required(conversation_id, "conversation_id")
        async with self._connect() as database:
            cursor = await database.execute(
                "DELETE FROM evidence WHERE conversation_id = ?",
                (normalized,),
            )
            await database.commit()
        return max(cursor.rowcount, 0)

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        database = await aiosqlite.connect(self.database_path)
        database.row_factory = aiosqlite.Row
        try:
            yield database
        finally:
            await database.close()


def _record_from_row(row: aiosqlite.Row) -> EvidenceRecord:
    return EvidenceRecord(
        id=row["id"],
        conversation_id=row["conversation_id"],
        run_id=row["run_id"],
        tool_call_id=row["tool_call_id"],
        tool_name=row["tool_name"],
        content_type=row["content_type"],
        content_chars=row["content_chars"],
        content_bytes=row["content_bytes"],
        sha256=row["sha256"],
        task_id=row["task_id"],
        task_step_id=row["task_step_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _snippet(content: str, query: str, *, radius: int = 180) -> str:
    index = content.casefold().find(query.casefold())
    if index < 0:
        return content[: radius * 2]
    start = max(0, index - radius)
    end = min(len(content), index + len(query) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


def _required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


__all__ = [
    "DEFAULT_MAX_EVIDENCE_ITEM_BYTES",
    "DEFAULT_MAX_EVIDENCE_TOTAL_BYTES",
    "EvidenceCapacityError",
    "SQLiteEvidenceStore",
]
