"""Evidence FTS5 检索投影测试（P1：内部升级，公共接口不变）。

覆盖：中文 / 英文 / 大文本检索、分页、会话隔离、tool/task 过滤、
短查询回退、投影损坏自愈重建、原文不受投影影响。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.evidence import SQLiteEvidenceStore


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def _seed(
    store: SQLiteEvidenceStore,
    conversation_id: str,
    items: list[tuple[str, str, str]],
) -> None:
    """items: (tool_call_id, tool_name, content)。"""

    for index, (tool_call_id, tool_name, content) in enumerate(items):
        await store.create(
            conversation_id=conversation_id,
            run_id=f"run-{conversation_id}",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=content,
            sha256=_digest(content),
            task_id=None if index == 0 else "task-1",
        )


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteEvidenceStore:
    store = SQLiteEvidenceStore(tmp_path / "vesta.db")
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_fts_projection_is_active(store) -> None:
    """初始化后 FTS 投影就绪（真的走索引路径，而非静默降级）。"""

    assert store._fts_ready is True
    await store.create(
        conversation_id="conv-1",
        run_id="run-1",
        tool_call_id="t1",
        tool_name="read_file",
        content="部署脚本 deploy/RELEASE-9F27.sh 执行成功",
        sha256=_digest("x"),
    )

    called_scan = False

    async def _fail_scan(**kwargs):
        nonlocal called_scan
        called_scan = True
        raise AssertionError("FTS 就绪时 ≥3 字符查询不应走扫描路径")

    original = store._search_scan_rows
    store._search_scan_rows = _fail_scan  # type: ignore[method-assign]
    try:
        hits = await store.search(conversation_id="conv-1", query="RELEASE-9F27")
    finally:
        store._search_scan_rows = original  # type: ignore[method-assign]

    assert called_scan is False
    assert len(hits) == 1
    assert "RELEASE-9F27" in hits[0].snippet


@pytest.mark.asyncio
async def test_chinese_and_english_search(store) -> None:
    await _seed(
        store,
        "conv-1",
        [
            ("t1", "run_shell_command", "数据库迁移到 PostgreSQL 16 完成"),
            ("t2", "run_shell_command", "前端构建从 webpack 换成 vite"),
            ("t3", "read_file", "release notes: fixed memory leak"),
        ],
    )

    chinese = await store.search(conversation_id="conv-1", query="数据库迁移")
    assert [hit.record.tool_call_id for hit in chinese] == ["t1"]

    english = await store.search(conversation_id="conv-1", query="memory leak")
    assert [hit.record.tool_call_id for hit in english] == ["t3"]

    phrase = await store.search(conversation_id="conv-1", query="webpack 换成")
    assert [hit.record.tool_call_id for hit in phrase] == ["t2"]


@pytest.mark.asyncio
async def test_large_text_and_pagination(store) -> None:
    large = ("大数据块内容。" * 2_000) + "NEEDLE-标记-END" + ("尾部填充。" * 500)
    items = [(f"t{i}", "read_file", f"普通条目 {i}") for i in range(15)]
    items.append(("t-big", "read_file", large))
    await _seed(store, "conv-1", items)

    hits = await store.search(conversation_id="conv-1", query="NEEDLE-标记")
    assert len(hits) == 1
    assert hits[0].record.tool_call_id == "t-big"
    assert "NEEDLE-标记" in hits[0].snippet

    # 分页：普通条目查询 + limit 逐步收窄。
    all_hits = await store.search(
        conversation_id="conv-1", query="普通条目", limit=20
    )
    assert len(all_hits) == 15
    page = await store.search(conversation_id="conv-1", query="普通条目", limit=5)
    assert len(page) == 5
    assert page[0].record.created_at >= page[-1].record.created_at


@pytest.mark.asyncio
async def test_conversation_isolation_and_filters(store) -> None:
    await _seed(
        store,
        "conv-a",
        [
            ("a1", "run_shell_command", "共享关键词 ALPHA"),
            ("a2", "read_file", "共享关键词 ALPHA 只读"),
        ],
    )
    await _seed(
        store,
        "conv-b",
        [("b1", "run_shell_command", "共享关键词 ALPHA")],
    )

    hits_a = await store.search(conversation_id="conv-a", query="共享关键词")
    assert {hit.record.tool_call_id for hit in hits_a} == {"a1", "a2"}
    hits_b = await store.search(conversation_id="conv-b", query="共享关键词")
    assert [hit.record.tool_call_id for hit in hits_b] == ["b1"]

    shell_only = await store.search(
        conversation_id="conv-a",
        query="ALPHA",
        tool_name="read_file",
    )
    assert [hit.record.tool_call_id for hit in shell_only] == ["a2"]

    task_only = await store.search(
        conversation_id="conv-a",
        query="ALPHA",
        task_id="task-1",
    )
    assert [hit.record.tool_call_id for hit in task_only] == ["a2"]


@pytest.mark.asyncio
async def test_short_query_falls_back_to_scan(store) -> None:
    """<3 字符查询走 instr 回退（trigram 无法匹配），结果仍正确。"""

    await _seed(store, "conv-1", [("t1", "read_file", "ab 关键内容")])

    hits = await store.search(conversation_id="conv-1", query="ab")
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_silent_projection_damage_heals_via_forced_rebuild(store) -> None:
    """静默损坏（不抛错、计数也对不上检测）时：清状态标记触发全量重建。"""

    await _seed(store, "conv-1", [("t1", "read_file", "自愈标记 SELFHEAL 内容")])
    async with store._connect() as database:
        await database.execute(
            "INSERT INTO evidence_fts(evidence_fts) VALUES ('delete-all')"
        )
        await database.commit()

    # 静默损坏不影响原文，只影响检索命中。
    assert len(await store.list_recent(conversation_id="conv-1")) == 1
    assert await store.search(conversation_id="conv-1", query="SELFHEAL") == ()

    # 文档化修复路径：清重建标记后重新 initialize 触发全量重建。
    async with store._connect() as database:
        await database.execute("DELETE FROM evidence_fts_state")
        await database.commit()
    await store.initialize()

    hits = await store.search(conversation_id="conv-1", query="SELFHEAL")
    assert len(hits) == 1
    assert store._fts_ready is True


@pytest.mark.asyncio
async def test_row_count_mismatch_triggers_rebuild(store) -> None:
    """投影行数与原文不一致（如中断/手工删行）时：启动对账自动重建。"""

    await _seed(store, "conv-1", [("t1", "read_file", "对账标记 AUDIT 内容")])
    async with store._connect() as database:
        # 制造行数不一致：删除一条原文但绕过触发器（模拟中断遗留）。
        await database.execute("DROP TRIGGER evidence_fts_ad")
        await database.execute("DELETE FROM evidence WHERE tool_call_id = 't1'")
        await database.commit()
    await _seed(store, "conv-1", [("t2", "read_file", "对账标记 AUDIT 新内容")])

    # evidence=1 行、投影残留 2 条索引：对账发现不一致后重建。
    await store.initialize()
    hits = await store.search(conversation_id="conv-1", query="AUDIT")

    assert len(hits) == 1
    assert hits[0].record.tool_call_id == "t2"


@pytest.mark.asyncio
async def test_missing_projection_degrades_to_scan(store) -> None:
    """投影表丢失：检索降级 instr 扫描，结果正确；原文不受影响。"""

    await _seed(store, "conv-1", [("t1", "read_file", "降级标记 FALLBACK 内容")])
    async with store._connect() as database:
        await database.execute("DROP TABLE evidence_fts")
        await database.commit()

    hits = await store.search(conversation_id="conv-1", query="FALLBACK")

    assert len(hits) == 1
    assert "FALLBACK" in hits[0].snippet
    assert store._fts_ready is False


@pytest.mark.asyncio
async def test_projection_loss_never_affects_original(store) -> None:
    """删除投影表后原文仍可读；重新 initialize 走全量重建恢复检索。"""

    await _seed(store, "conv-1", [("t1", "read_file", "重建标记 REBUILD 内容")])
    evidence_id = (await store.list_recent(conversation_id="conv-1"))[0].id

    async with store._connect() as database:
        await database.execute("DROP TABLE evidence_fts")
        await database.execute("DELETE FROM evidence_fts_state")
        await database.commit()
    store._fts_ready = False

    document = await store.resolve(evidence_id[:8], conversation_id="conv-1")
    assert document is not None
    assert "REBUILD" in document.content

    await store.initialize()
    hits = await store.search(conversation_id="conv-1", query="REBUILD")
    assert len(hits) == 1
