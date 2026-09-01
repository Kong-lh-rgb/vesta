"""普通长期记忆的混合检索索引（SQLite 投影：FTS5 + 向量 + RRF 融合）。

定位与不变量：
- Markdown 文件（active/Mxxx.md）永远是唯一权威存储；本索引是可删除、
  可重建的搜索投影，任何索引失败都不影响 Markdown 读写与 Host 启动；
- 只索引 active 记忆；archive 时删除对应行，归档记忆默认不可检索；
- Chunk 保存 revision、正文 sha256、embedding model 与 dimensions，
  update 后旧 Chunk 依据 sha256 / revision 失效重算；
- 检索 = FTS5（trigram，支持中文精确关键词）+ 向量余弦（语义改写），
  两路排名用 RRF 融合并按 memory_id 合并 Chunk，取最相关片段做摘要；
- Embedding 缺失或调用失败时自动降级为 FTS5 单路，绝不让 Run 失败。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from array import array
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import aiosqlite

from .embedding import EmbeddingAdapter
from .models import MemoryRecord, MemoryStatus

logger = logging.getLogger("vesta.memory.search_index")

DEFAULT_SEARCH_DATABASE_NAME = "search.sqlite"
_SCHEMA_VERSION = 2
_RRF_K = 60


class SearchMode(StrEnum):
    """一次检索实际使用的融合模式。"""

    HYBRID = "hybrid"
    VECTOR = "vector"
    FTS = "fts"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class MemorySearchCandidate:
    """一个按 memory_id 合并后的检索候选。"""

    memory_id: str
    title: str
    summary: str
    revision: int
    snippet: str
    rrf_score: float
    matched_by_vector: bool
    matched_by_fts: bool


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """一次检索的完整结果（含降级信息）。"""

    mode: SearchMode
    candidates: tuple[MemorySearchCandidate, ...]
    query: str
    degrade_reason: str | None = None


class MemorySearchSettings:
    """检索与召回的运行参数（纯代码常量，不引入额外环境变量面）。"""

    def __init__(
        self,
        *,
        top_k: int = 5,
        chunk_chars: int = 900,
        chunk_overlap_chars: int = 180,
        max_chunks_per_memory: int = 16,
        candidate_multiplier: int = 8,
        min_vector_similarity: float = 0.12,
        snippet_chars: int = 360,
        recall_message_max_chars: int = 2_400,
        query_max_chars: int = 1_600,
    ) -> None:
        if top_k <= 0 or chunk_chars <= 0:
            raise ValueError("search settings limits must be positive")
        if not 0 <= chunk_overlap_chars < chunk_chars:
            raise ValueError("chunk overlap must be within [0, chunk_chars)")
        if not 0.0 <= min_vector_similarity < 1.0:
            raise ValueError("min_vector_similarity must be within [0, 1)")
        self.top_k = top_k
        self.chunk_chars = chunk_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self.max_chunks_per_memory = max_chunks_per_memory
        self.candidate_multiplier = candidate_multiplier
        # 过滤向量路径的弱命中：无关文本之间的余弦并非零（哈希碰撞或真实
        # Embedding 的普遍正值），低于该阈值不参与融合。
        self.min_vector_similarity = min_vector_similarity
        self.snippet_chars = snippet_chars
        self.recall_message_max_chars = recall_message_max_chars
        self.query_max_chars = query_max_chars


_SCHEMA_CHUNKS = """
CREATE TABLE IF NOT EXISTS memory_chunks (
    memory_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    embedding_model TEXT,
    embedding_dim INTEGER,
    embedding BLOB,
    PRIMARY KEY (memory_id, chunk_index)
);
"""

_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS search_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def chunk_memory_text(
    record: MemoryRecord,
    *,
    settings: MemorySearchSettings,
) -> tuple[tuple[str, str], ...]:
    """把一条记忆切成 (chunk 文本, 正文 sha256) 列表。

    Chunk 文本带 ``title | summary`` 语义头部，让向量与 FTS 都能利用
    Recall Cue；正文按段落累积切块并保留少量重叠。
    """

    header = f"{record.title} | {record.summary}"
    paragraphs = [part.strip() for part in record.content.split("\n\n")]
    bodies: list[str] = []
    current: list[str] = []
    used = 0
    for paragraph in paragraphs:
        if not paragraph:
            continue
        addition = len(paragraph) + (1 if current else 0)
        if current and used + addition > settings.chunk_chars:
            bodies.append("\n\n".join(current))
            overlap = "\n\n".join(current)[-settings.chunk_overlap_chars :].lstrip()
            current = [overlap] if overlap else []
            used = len(overlap)
        current.append(paragraph)
        used += addition
    if current:
        bodies.append("\n\n".join(current))
    if not bodies:
        bodies = [record.content]
    bodies = bodies[: settings.max_chunks_per_memory]
    chunks: list[tuple[str, str]] = []
    for body in bodies:
        text = f"{header}\n{body}"[: max(settings.chunk_chars * 2, len(header) + 200)]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunks.append((text, digest))
    return tuple(chunks)


def _fts_match_expression(query: str, *, max_terms: int = 12) -> str | None:
    """把自由文本 Query 转成安全的 FTS5 OR 短语表达式。"""

    terms: list[str] = []
    for raw in query.replace("\r", " ").replace("\n", " ").split():
        term = raw.strip().strip("\"'()*")
        if len(term) < 2:
            continue
        terms.append(term)
    if not terms:
        return None
    expressions = [f'"{term}"' for term in terms[:max_terms]]
    return " OR ".join(expressions)


def _cosine_similarity(
    left: array,
    right: array,
) -> float:
    if len(left) != len(right) or not len(left):
        return 0.0
    dot = 0.0
    for index in range(len(left)):
        dot += left[index] * right[index]
    if dot == 0.0:
        return 0.0
    return dot  # 索引与查询向量均已归一化，点积即余弦。


def _decode_embedding(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


def _normalize_vector(vector: tuple[float, ...]) -> tuple[tuple[float, ...], bytes]:
    norm = math.sqrt(sum(value * value for value in vector))
    normalized = (
        tuple(value / norm for value in vector) if norm > 0 else tuple(vector)
    )
    return normalized, array("f", normalized).tobytes()


class MemorySearchIndex:
    """SQLite FTS5 + 向量的混合检索投影。"""

    def __init__(
        self,
        database_path: str | Path,
        *,
        embedding: EmbeddingAdapter | None,
        settings: MemorySearchSettings | None = None,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.embedding = embedding
        self.settings = settings or MemorySearchSettings()
        self._write_lock = asyncio.Lock()
        self._fts_available = False
        self._initialized = False

    # ------------------------------------------------------------------
    # 初始化与重建
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """建表并探测 FTS5；结构不兼容时删除重建（投影可丢弃）。"""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._open_schema()
        except aiosqlite.Error:
            # 损坏或结构过期的投影文件：直接删除后重建一次。
            logger.warning(
                "memory search index unreadable, rebuilding: %s",
                self.database_path,
            )
            self.database_path.unlink(missing_ok=True)
            await self._open_schema()
        self._initialized = True

    async def _open_schema(self) -> None:
        async with self._connect() as database:
            await database.execute("PRAGMA journal_mode=WAL")
            await database.executescript(_SCHEMA_META)
            await database.executescript(_SCHEMA_CHUNKS)
            stored_version = await self._meta_get(database, "schema_version")
            if stored_version != str(_SCHEMA_VERSION):
                await database.execute("DROP TABLE IF EXISTS memory_fts")
                await database.execute("DELETE FROM memory_chunks")
                await self._meta_set(database, "schema_version", _SCHEMA_VERSION)
            tokenizer = await self._ensure_fts_table(database)
            await self._meta_set(database, "fts_tokenizer", tokenizer)
            await database.commit()

    async def _ensure_fts_table(self, database: aiosqlite.Connection) -> str:
        for tokenizer in ("trigram", "unicode61"):
            try:
                await database.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
                    "text, memory_id UNINDEXED, chunk_index UNINDEXED, "
                    f"tokenize='{tokenizer}')"
                )
                await database.commit()
                self._fts_available = True
                return tokenizer
            except aiosqlite.Error as exc:
                logger.info("fts5 tokenizer %s unavailable: %s", tokenizer, exc)
        self._fts_available = False
        return "none"

    async def reconcile(
        self,
        records: tuple[MemoryRecord, ...],
    ) -> None:
        """以 Markdown 为权威对账：删多余行、重算缺失或过期的 Chunk。"""

        if not self._initialized:
            return
        active_ids = {
            record.id for record in records if record.status is MemoryStatus.ACTIVE
        }
        async with self._write_lock:
            async with self._connect() as database:
                indexed_ids = {
                    row[0]
                    for row in await database.execute_fetchall(
                        "SELECT DISTINCT memory_id FROM memory_chunks"
                    )
                }
            for stale_id in sorted(indexed_ids - active_ids):
                await self._remove_rows(stale_id)
            for record in records:
                if record.status is not MemoryStatus.ACTIVE:
                    continue
                await self._upsert_rows(record)

    # ------------------------------------------------------------------
    # 增量同步（create / update / archive 后调用）
    # ------------------------------------------------------------------

    async def upsert(self, record: MemoryRecord) -> None:
        if not self._initialized:
            return
        async with self._write_lock:
            await self._upsert_rows(record)

    async def remove(self, memory_id: str) -> None:
        if not self._initialized:
            return
        async with self._write_lock:
            await self._remove_rows(memory_id)

    async def _upsert_rows(self, record: MemoryRecord) -> None:
        chunks = chunk_memory_text(record, settings=self.settings)
        model_name = self._embedding_model_name
        try:
            async with self._connect() as database:
                rows = await database.execute_fetchall(
                    "SELECT chunk_index, text_sha256, embedding_model, embedding "
                    "FROM memory_chunks WHERE memory_id = ?",
                    (record.id,),
                )
                existing = {row[0]: (row[1], row[2], row[3]) for row in rows}
                reusable: list[int] = []
                pending: list[tuple[int, str, str]] = []
                for index, (text, digest) in enumerate(chunks):
                    current = existing.get(index)
                    if (
                        current is not None
                        and current[0] == digest
                        and current[1] == model_name
                        and (current[2] is not None or self.embedding is None)
                    ):
                        # 内容、模型与向量都未变化：只刷新 revision。
                        reusable.append(index)
                    else:
                        pending.append((index, text, digest))
                for index in existing:
                    if index >= len(chunks):
                        await self._delete_chunk(database, record.id, index)
                if reusable:
                    placeholders = ",".join("?" * len(reusable))
                    await database.execute(
                        "UPDATE memory_chunks SET revision = ? "
                        f"WHERE memory_id = ? AND chunk_index IN ({placeholders})",
                        (record.revision, record.id, *reusable),
                    )
                if pending:
                    vectors = await self._embed_texts(
                        tuple(item[1] for item in pending)
                    )
                    for position, (index, text, digest) in enumerate(pending):
                        vector = vectors[position] if vectors is not None else None
                        if vector is not None:
                            normalized, blob = _normalize_vector(vector)
                            dim = len(normalized)
                            model = model_name
                        else:
                            blob = None
                            dim = None
                            model = None
                        await self._delete_chunk(database, record.id, index)
                        await database.execute(
                            "INSERT OR REPLACE INTO memory_chunks ("
                            "memory_id, chunk_index, revision, title, summary, "
                            "text, text_sha256, embedding_model, embedding_dim, "
                            "embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                record.id,
                                index,
                                record.revision,
                                record.title,
                                record.summary,
                                text,
                                digest,
                                model,
                                dim,
                                blob,
                            ),
                        )
                        if self._fts_available:
                            await database.execute(
                                "INSERT INTO memory_fts ("
                                "text, memory_id, chunk_index) VALUES (?, ?, ?)",
                                (text, record.id, index),
                            )
                await database.commit()
        except Exception as exc:
            # 增量同步失败只降级检索质量，绝不破坏 Markdown 写入路径。
            logger.warning(
                "memory search index sync failed for %s: %s",
                record.id,
                exc,
            )

    async def _remove_rows(self, memory_id: str) -> None:
        try:
            async with self._connect() as database:
                await database.execute(
                    "DELETE FROM memory_chunks WHERE memory_id = ?",
                    (memory_id,),
                )
                if self._fts_available:
                    await database.execute(
                        "DELETE FROM memory_fts WHERE memory_id = ?",
                        (memory_id,),
                    )
                await database.commit()
        except aiosqlite.Error as exc:
            logger.warning(
                "memory search index remove failed for %s: %s",
                memory_id,
                exc,
            )

    async def _delete_chunk(
        self,
        database: aiosqlite.Connection,
        memory_id: str,
        chunk_index: int,
    ) -> None:
        await database.execute(
            "DELETE FROM memory_chunks WHERE memory_id = ? AND chunk_index = ?",
            (memory_id, chunk_index),
        )
        if self._fts_available:
            await database.execute(
                "DELETE FROM memory_fts WHERE memory_id = ? AND chunk_index = ?",
                (memory_id, chunk_index),
            )

    async def _embed_texts(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...] | None:
        if self.embedding is None:
            return None
        try:
            return await self.embedding.embed_documents(texts)
        except Exception as exc:
            logger.warning("memory embedding batch failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
    ) -> MemorySearchResult:
        """Hybrid 检索；向量失败自动降级 FTS5，FTS 缺失退化为向量单路。"""

        if not self._initialized:
            return MemorySearchResult(
                mode=SearchMode.UNAVAILABLE,
                candidates=(),
                query=query,
                degrade_reason="index not initialized",
            )
        effective_limit = limit or self.settings.top_k
        fetch = max(
            effective_limit * self.settings.candidate_multiplier,
            effective_limit,
        )
        degrade_reason: str | None = None

        vector_hits = await self._vector_search(query, fetch)
        if vector_hits is None:
            degrade_reason = "embedding unavailable or failed"
        fts_hits = await self._fts_search(query, fetch)
        if fts_hits is None and vector_hits is None:
            return MemorySearchResult(
                mode=SearchMode.UNAVAILABLE,
                candidates=(),
                query=query,
                degrade_reason=degrade_reason or "no retrieval path available",
            )

        scores: dict[str, float] = {}
        best_chunk: dict[str, tuple[float, str]] = {}
        matched_vector: set[str] = set()
        matched_fts: set[str] = set()
        for rank, hit in enumerate(vector_hits or (), start=1):
            scores[hit.memory_id] = scores.get(hit.memory_id, 0.0) + 1.0 / (
                _RRF_K + rank
            )
            matched_vector.add(hit.memory_id)
            _keep_best_chunk(best_chunk, hit)
        for rank, hit in enumerate(fts_hits or (), start=1):
            scores[hit.memory_id] = scores.get(hit.memory_id, 0.0) + 1.0 / (
                _RRF_K + rank
            )
            matched_fts.add(hit.memory_id)
            _keep_best_chunk(best_chunk, hit)

        ordered = sorted(scores, key=lambda memory_id: (-scores[memory_id], memory_id))
        candidates = tuple(
            MemorySearchCandidate(
                memory_id=memory_id,
                title=best_chunk[memory_id][1],
                summary="",
                revision=0,
                snippet=best_chunk[memory_id][2][: self.settings.snippet_chars],
                rrf_score=scores[memory_id],
                matched_by_vector=memory_id in matched_vector,
                matched_by_fts=memory_id in matched_fts,
            )
            for memory_id in ordered[:effective_limit]
        )
        if vector_hits is not None and fts_hits is not None:
            mode = SearchMode.HYBRID
        elif vector_hits is not None:
            mode = SearchMode.VECTOR
        else:
            mode = SearchMode.FTS
        return MemorySearchResult(
            mode=mode,
            candidates=candidates,
            query=query,
            degrade_reason=degrade_reason,
        )

    async def _vector_search(
        self,
        query: str,
        fetch: int,
    ) -> tuple[_ChunkHit, ...] | None:
        if self.embedding is None:
            return None
        try:
            query_vector_raw = await self.embedding.embed_query(query)
        except Exception as exc:
            logger.warning("memory query embedding failed: %s", exc)
            return None
        query_vector, _ = _normalize_vector(query_vector_raw)
        try:
            async with self._connect() as database:
                rows = await database.execute_fetchall(
                    "SELECT memory_id, chunk_index, title, text, embedding "
                    "FROM memory_chunks WHERE embedding IS NOT NULL"
                )
        except aiosqlite.Error as exc:
            logger.warning("memory vector search failed: %s", exc)
            return None
        hits: list[_ChunkHit] = []
        for memory_id, chunk_index, title, text, blob in rows:
            vector = _decode_embedding(blob)
            if len(vector) != len(query_vector):
                continue
            similarity = _cosine_similarity(array("f", query_vector), vector)
            if similarity < self.settings.min_vector_similarity:
                continue
            hits.append(
                _ChunkHit(
                    memory_id=memory_id,
                    chunk_index=chunk_index,
                    title=title or "",
                    text=text or "",
                    score=similarity,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.memory_id, hit.chunk_index))
        return tuple(hits[:fetch])

    async def _fts_search(
        self,
        query: str,
        fetch: int,
    ) -> tuple[_ChunkHit, ...] | None:
        if not self._fts_available:
            return None
        expression = _fts_match_expression(query)
        if expression is None:
            return None
        try:
            async with self._connect() as database:
                rows = await database.execute_fetchall(
                    "SELECT memory_id, chunk_index, text FROM memory_fts "
                    "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                    (expression, fetch),
                )
        except aiosqlite.Error as exc:
            logger.warning("memory fts search failed: %s", exc)
            return None
        return tuple(
            _ChunkHit(
                memory_id=memory_id,
                chunk_index=chunk_index,
                title="",
                text=text or "",
                score=0.0,
            )
            for memory_id, chunk_index, text in rows
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @property
    def _embedding_model_name(self) -> str | None:
        return self.embedding.model_name if self.embedding is not None else None

    def _connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.database_path)

    @staticmethod
    async def _meta_get(
        database: aiosqlite.Connection,
        key: str,
    ) -> str | None:
        rows = await database.execute_fetchall(
            "SELECT value FROM search_meta WHERE key = ?",
            (key,),
        )
        return rows[0][0] if rows else None

    @staticmethod
    async def _meta_set(
        database: aiosqlite.Connection,
        key: str,
        value: str,
    ) -> None:
        await database.execute(
            "INSERT OR REPLACE INTO search_meta (key, value) VALUES (?, ?)",
            (key, value),
        )


@dataclass(frozen=True, slots=True)
class _ChunkHit:
    """单路检索返回的一个 Chunk 命中。"""

    memory_id: str
    chunk_index: int
    title: str
    text: str
    score: float


def _keep_best_chunk(
    best_chunk: dict[str, tuple[float, str, str]],
    hit: _ChunkHit,
) -> None:
    current = best_chunk.get(hit.memory_id)
    if current is None or hit.score > current[0]:
        best_chunk[hit.memory_id] = (hit.score, hit.title or "", hit.text)


__all__ = [
    "DEFAULT_SEARCH_DATABASE_NAME",
    "MemorySearchCandidate",
    "MemorySearchIndex",
    "MemorySearchResult",
    "MemorySearchSettings",
    "SearchMode",
]
