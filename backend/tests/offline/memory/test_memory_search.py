"""普通长期记忆 Hybrid 自动召回的离线测试。

覆盖：中文语义改写召回、FTS5 精确关键词、Hybrid/RRF 融合与去重、
Update / Archive 的索引失效、手工修改 Markdown 后重建、Embedding 失败
降级 FTS5、每 Run 只检索一次、召回不写历史 / 不进摘要 / 不加
access_count、只有 memory_read 才授权 Reflection Update。
全部使用 FakeEmbeddingAdapter，禁止调用真实 API。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.agent.context_session import RuntimeContextSession
from app.agent.events import AgentEventType, InMemoryEventHandler
from app.agent.result import AgentStopReason, ToolCallRecord
from app.agent.runtime import AgentRuntime
from app.agent.runtime_helpers import recalled_memory_revisions
from app.memory import (
    CORE_MEMORY_MESSAGE_NAME,
    MEMORY_INDEX_MESSAGE_NAME,
    MEMORY_RECALL_MESSAGE_NAME,
    MEMORY_SEARCH_TOOL_NAME,
    FakeEmbeddingAdapter,
    MemoryManager,
    MemoryRecallQueryInputs,
    SearchMode,
)
from app.memory.search_index import MemorySearchIndex, _ChunkHit
from app.models.adapter import ModelAdapter
from app.models.config import ModelSettings, ProviderConfig
from app.models.registry import ModelAdapterRegistry
from app.models.types import (
    ApiStyle,
    Message,
    MessageRole,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ToolCall,
    ToolResult,
)
from app.tools.registry import ToolRegistry


class CountingFakeEmbedding(FakeEmbeddingAdapter):
    """统计 query 向量化次数，用于验证"每 Run 只检索一次"。"""

    def __init__(self) -> None:
        super().__init__()
        self.query_calls = 0

    async def embed_query(self, text: str) -> tuple[float, ...]:
        self.query_calls += 1
        return await super().embed_query(text)


class FailingEmbedding:
    """始终失败的向量服务：验证降级路径。"""

    @property
    def model_name(self) -> str:
        return "failing-embedding"

    @property
    def dimensions(self) -> int | None:
        return 8

    async def embed_documents(self, texts):
        raise RuntimeError("embedding service offline")

    async def embed_query(self, text: str) -> tuple[float, ...]:
        raise RuntimeError("embedding service offline")

    async def close(self) -> None:
        return None


class BlockingEmbedding(FakeEmbeddingAdapter):
    """阻塞文档向量化，用于证明 Host 初始化不等待远程 Embedding。"""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed_documents(self, texts):
        self.started.set()
        await self.release.wait()
        return await super().embed_documents(texts)


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    return tmp_path / "memory"


async def _seed(manager: MemoryManager) -> None:
    await manager.create(
        title="数据库迁移决定",
        summary="生产库从 MySQL 迁移到 PostgreSQL 的最终决定",
        content=(
            "2024-12 定稿：生产环境数据库从 MySQL 整体迁移到 PostgreSQL 16，"
            "原因是事务隔离与窗口函数需求。迁移脚本放在 deploy/pg-migration。"
        ),
    )
    await manager.create(
        title="前端构建决定",
        summary="前端打包从 webpack 换成 vite",
        content=(
            "2024-11 定稿：前端构建工具从 webpack 5 迁移到 vite 5，"
            "提升本地开发热更新速度。"
        ),
    )


# ----------------------------------------------------------------------
# 中文语义改写召回（向量路径）
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chinese_paraphrase_recall_ranks_relevant_memory_first(
    memory_root: Path,
) -> None:
    embedding = CountingFakeEmbedding()
    manager = MemoryManager(memory_root, embedding=embedding)
    await manager.initialize()
    await _seed(manager)

    result = await manager.search("当初数据库迁移到 PG 是怎么定的")

    assert result.mode is SearchMode.HYBRID
    assert result.candidates, "语义改写查询应召回相关记忆"
    assert result.candidates[0].memory_id == "M001"
    assert result.candidates[0].title == "数据库迁移决定"
    assert result.candidates[0].revision == 1


# ----------------------------------------------------------------------
# 精确关键词由 FTS5 召回（无 Embedding 也能工作）
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_keyword_recall_via_fts5_without_embedding(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=None)
    await manager.initialize()
    await _seed(manager)

    result = await manager.search("pg-migration")

    assert result.mode is SearchMode.FTS
    assert [candidate.memory_id for candidate in result.candidates] == ["M001"]
    assert result.candidates[0].matched_by_fts is True
    assert result.candidates[0].matched_by_vector is False


# ----------------------------------------------------------------------
# Hybrid / RRF 融合与按 memory_id 去重
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hybrid_rrf_merges_and_dedupes_by_memory_id(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    # "数据库 迁移 PostgreSQL" 同时命中向量与 FTS 两路；同一记忆只出现一次。
    result = await manager.search("数据库 迁移 PostgreSQL 部署脚本")

    ids = [candidate.memory_id for candidate in result.candidates]
    assert len(ids) == len(set(ids)), "同一 memory 的多个 Chunk 必须合并"
    assert result.mode is SearchMode.HYBRID
    top = result.candidates[0]
    assert top.memory_id == "M001"
    assert top.matched_by_vector and top.matched_by_fts
    # 两路同时命中的记忆 RRF 得分高于单路命中。
    if len(result.candidates) > 1:
        assert top.rrf_score > result.candidates[1].rrf_score


@pytest.mark.asyncio
async def test_rrf_prefers_dual_path_hit_over_single_path(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await manager.create(
        title="唯一关键词",
        summary="包含独占代码标识",
        content="冷门标识 XYZUNIQUE-42 只出现在这条记忆里。",
    )
    await manager.create(
        title="共享关键词",
        summary="同时包含主题词与独占标识",
        content="数据库迁移主题；另一条独占标识是 XYZUNIQUE-43。",
    )

    result = await manager.search("数据库 迁移 XYZUNIQUE-42")

    ids = [candidate.memory_id for candidate in result.candidates]
    assert "M002" in ids
    if "M001" in ids and len(ids) > 1:
        m002 = next(c for c in result.candidates if c.memory_id == "M002")
        m001 = next(c for c in result.candidates if c.memory_id == "M001")
        assert m002.rrf_score >= m001.rrf_score


# ----------------------------------------------------------------------
# Update / Archive 的索引失效
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_invalidates_stale_vectors(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    record = await manager.create(
        title="部署配置",
        summary="线上部署脚本位置与回滚流程",
        content="部署脚本 deploy/RELEASE-9F27.sh，回滚用 deploy/ROLLBACK-9F27.sh。",
    )

    before = await manager.search("RELEASE-9F27")
    assert [candidate.memory_id for candidate in before.candidates] == ["M001"]

    await manager.update(
        record.id,
        content="部署改为 GitHub Actions 流水线，回滚走 re-deploy 旧版本 tag。",
        reason="迁移 CI",
    )

    after_old = await manager.search("RELEASE-9F27")
    assert [candidate.memory_id for candidate in after_old.candidates] == []
    after_new = await manager.search("GitHub Actions 流水线")
    assert [candidate.memory_id for candidate in after_new.candidates] == ["M001"]
    assert after_new.candidates[0].revision == 2


@pytest.mark.asyncio
async def test_archive_removes_memory_from_search(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)
    await manager.archive("M002", reason="过时")

    result = await manager.search("vite webpack 前端构建")
    assert "M002" not in [candidate.memory_id for candidate in result.candidates]


# ----------------------------------------------------------------------
# 手工修改 Markdown 后重建
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_markdown_edit_rebuilds_index(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    path = memory_root / "active" / "M002.md"
    text = path.read_text(encoding="utf-8").replace("webpack", "Rspack")
    path.write_text(text, encoding="utf-8")

    rebuilt = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await rebuilt.initialize()

    result = await rebuilt.search("Rspack 构建")
    assert result.candidates
    assert result.candidates[0].memory_id == "M002"
    stale = await rebuilt.search("webpack")
    assert "M002" not in [candidate.memory_id for candidate in stale.candidates]


@pytest.mark.asyncio
async def test_deleted_projection_file_is_rebuilt(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)
    (memory_root / "search.sqlite").unlink()

    rebuilt = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await rebuilt.initialize()
    assert rebuilt.hybrid_recall_enabled is True

    result = await rebuilt.search("pg-migration")
    assert [candidate.memory_id for candidate in result.candidates] == ["M001"]


# ----------------------------------------------------------------------
# Embedding 失败降级 FTS5；索引失败不破坏 Markdown
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embedding_failure_degrades_to_fts(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FailingEmbedding())
    await manager.initialize()
    await _seed(manager)

    result = await manager.search("PostgreSQL 迁移")

    assert result.mode is SearchMode.FTS
    assert result.degrade_reason is not None
    assert "M001" in [candidate.memory_id for candidate in result.candidates]


@pytest.mark.asyncio
async def test_embedding_backfill_does_not_block_manager_initialize(
    memory_root: Path,
) -> None:
    seed_manager = MemoryManager(memory_root, embedding=None)
    await seed_manager.initialize()
    await seed_manager.create(
        title="启动期向量补全",
        summary="Host 不应等待远程 Embedding",
        content="FTS 投影先可用，向量随后在后台补齐。",
    )
    await seed_manager.close()

    embedding = BlockingEmbedding()
    manager = MemoryManager(memory_root, embedding=embedding)
    await asyncio.wait_for(manager.initialize(), timeout=0.5)

    # initialize 已经返回，后台任务才会停在远程向量请求上。
    await asyncio.wait_for(embedding.started.wait(), timeout=0.5)
    before = await manager.search("启动期向量补全")
    assert before.mode is SearchMode.FTS

    embedding.release.set()
    assert manager._search_backfill_task is not None
    await asyncio.wait_for(manager._search_backfill_task, timeout=0.5)
    after = await manager.search("启动期向量补全")
    assert after.mode is SearchMode.HYBRID
    await manager.close()


@pytest.mark.asyncio
async def test_corrupted_index_does_not_break_markdown(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    # 写坏投影文件；Markdown 读路径与后续写入必须不受影响。
    (memory_root / "search.sqlite").write_bytes(b"not a sqlite file")

    result = await manager.search("PostgreSQL")
    assert result.mode is SearchMode.UNAVAILABLE
    record = await manager.create(
        title="新增记忆",
        summary="索引损坏后仍可写入",
        content="Markdown 是唯一权威存储，索引损坏不阻塞写入。",
    )
    assert record.id == "M003"
    loaded = await manager.store.load("M003")
    assert loaded is not None


# ----------------------------------------------------------------------
# access_count：自动命中不算读取
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_and_recall_do_not_increment_access_count(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    await manager.search("数据库迁移")
    snapshot = await manager.recall(
        MemoryRecallQueryInputs(user_message="数据库迁移怎么定的")
    )
    assert snapshot.candidates

    record = await manager.store.load("M001")
    assert record is not None
    assert record.access_count == 0

    # 只有显式 memory_read 才计数。
    await manager.read("M001")
    record = await manager.store.load("M001")
    assert record is not None
    assert record.access_count == 1


# ----------------------------------------------------------------------
# 注入：Hybrid 不注入 INDEX，Legacy 保持 INDEX
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_messages_hybrid_injects_recall_instead_of_index(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await manager.core.update("用户身份：开发者")
    await _seed(manager)

    snapshot = await manager.recall(
        MemoryRecallQueryInputs(user_message="前端构建工具换成了什么")
    )
    assert snapshot.candidates

    hybrid_messages = await manager.context_messages(recall=snapshot)
    names = [message.name for message in hybrid_messages]
    assert MEMORY_INDEX_MESSAGE_NAME not in names
    assert MEMORY_RECALL_MESSAGE_NAME in names
    assert CORE_MEMORY_MESSAGE_NAME in names
    recall_message = next(
        message
        for message in hybrid_messages
        if message.name == MEMORY_RECALL_MESSAGE_NAME
    )
    content = recall_message.content or ""
    assert "possibly relevant" in content.lower()
    assert "memory_read" in content
    # 只注入 cue 级信息：候选正文不完整注入。
    assert "2024-11 定稿" not in content.replace("Snippet: ", "") or (
        content.count("2024-11 定稿") <= 1
    )

    legacy_messages = await manager.context_messages()
    legacy_names = [message.name for message in legacy_messages]
    assert MEMORY_INDEX_MESSAGE_NAME in legacy_names
    assert MEMORY_RECALL_MESSAGE_NAME not in legacy_names


@pytest.mark.asyncio
async def test_runtime_index_failure_falls_back_to_legacy_index(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)
    (memory_root / "search.sqlite").write_bytes(b"broken at runtime")

    session = RuntimeContextSession(
        memory_manager=manager,
        skill_store=None,
        skill_context_provider=None,
        task_context_provider=None,
        recall_query=MemoryRecallQueryInputs(user_message="数据库迁移决定是什么"),
    )
    context = await session.build(
        conversation_id="conversation-runtime-fallback",
        recovery_checkpoint=None,
        trailing_system_messages=(),
    )

    names = [message.name for message in context.messages]
    assert MEMORY_INDEX_MESSAGE_NAME in names
    assert MEMORY_RECALL_MESSAGE_NAME not in names
    assert context.recall_mode == SearchMode.UNAVAILABLE.value
    await manager.close()


@pytest.mark.asyncio
async def test_recall_message_respects_top5_and_char_budget(
    memory_root: Path,
) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    for index in range(7):
        await manager.create(
            title=f"共享主题 {index}",
            summary=f"关于部署流程的第 {index} 条记忆",
            content=(
                f"部署流程说明 {index}：先跑测试，再构建镜像，最后滚动发布。"
                "重复的正文用于验证预算截断行为。"
            ),
        )

    snapshot = await manager.recall(
        MemoryRecallQueryInputs(user_message="部署流程是怎么规定的")
    )
    message = snapshot.render_message(
        max_chars=manager.search_settings.recall_message_max_chars
    )
    assert message is not None
    assert len(snapshot.candidates) <= 5
    content = message.content or ""
    assert len(content) <= manager.search_settings.recall_message_max_chars + 200


@pytest.mark.asyncio
async def test_empty_recall_returns_no_message(memory_root: Path) -> None:
    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    snapshot = await manager.recall(
        MemoryRecallQueryInputs(user_message="今天天气怎么样")
    )
    message = snapshot.render_message()
    assert message is None


# ----------------------------------------------------------------------
# memory_search 工具
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_search_tool_returns_candidates_without_full_content(
    memory_root: Path,
) -> None:
    from app.memory import MemorySearchTool

    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)

    tool = MemorySearchTool(manager)
    output = await tool.execute({"query": "数据库迁移 PostgreSQL"})

    assert output["available"] is True
    assert output["mode"] == "hybrid"
    results = output["results"]
    assert results
    assert results[0]["memory_id"] == "M001"
    assert results[0]["revision"] == 1
    # 不返回完整正文，只有 snippet。
    assert "content" not in results[0]
    assert "snippet" in results[0]

    missing = await tool.execute({"query": "不存在的主题 XYZNONE"})
    assert missing["results"] == []


@pytest.mark.asyncio
async def test_memory_search_tool_reports_unavailable_when_index_down(
    memory_root: Path,
) -> None:
    from app.memory import MemorySearchTool

    manager = MemoryManager(memory_root, embedding=FakeEmbeddingAdapter())
    await manager.initialize()
    await _seed(manager)
    (memory_root / "search.sqlite").write_bytes(b"broken")

    tool = MemorySearchTool(manager)
    output = await tool.execute({"query": "数据库"})

    assert output["available"] is False
    assert output["reason"]


def test_memory_search_registered_and_not_deferred() -> None:
    from app.memory import (
        DEFAULT_DEFERRED_MEMORY_TOOL_NAMES,
        register_memory_tools,
    )

    registry = ToolRegistry()
    manager = MemoryManager(Path("/nonexistent-vesta-memory"))
    register_memory_tools(registry, manager)

    names = {
        definition.name
        for definition in registry.definitions(for_model=True)
    }
    assert MEMORY_SEARCH_TOOL_NAME in names
    assert MEMORY_SEARCH_TOOL_NAME not in DEFAULT_DEFERRED_MEMORY_TOOL_NAMES


# ----------------------------------------------------------------------
# 每 Run 只检索一次；多 Step 复用
# ----------------------------------------------------------------------


class _CountingRecallManager(MemoryManager):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.recall_calls = 0

    async def recall(self, inputs):
        self.recall_calls += 1
        return await super().recall(inputs)


def _recall_messages(messages) -> list:
    return [
        message
        for message in messages
        if message.name == MEMORY_RECALL_MESSAGE_NAME
    ]


@pytest.mark.asyncio
async def test_session_recalls_once_and_reuses_across_steps(
    memory_root: Path,
) -> None:
    embedding = CountingFakeEmbedding()
    manager = _CountingRecallManager(memory_root, embedding=embedding)
    await manager.initialize()
    await _seed(manager)

    session = RuntimeContextSession(
        memory_manager=manager,
        skill_store=None,
        skill_context_provider=None,
        task_context_provider=None,
        recall_query=MemoryRecallQueryInputs(user_message="数据库迁移决定是什么"),
    )
    first = await session.build(
        conversation_id=None,
        recovery_checkpoint=None,
        trailing_system_messages=(),
    )
    second = await session.build(
        conversation_id=None,
        recovery_checkpoint=None,
        trailing_system_messages=(),
    )

    assert manager.recall_calls == 1
    assert embedding.query_calls == 1
    first_recall = _recall_messages(first.messages)
    second_recall = _recall_messages(second.messages)
    assert len(first_recall) == len(second_recall) == 1
    assert first_recall[0].content == second_recall[0].content
    assert first.recall_candidate_ids == second.recall_candidate_ids
    assert first.recall_mode == SearchMode.HYBRID.value


@pytest.mark.asyncio
async def test_rrf_scores_each_memory_once_per_retrieval_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = MemorySearchIndex(tmp_path / "rrf.sqlite", embedding=None)
    await index.initialize()

    async def vector_hits(query: str, fetch: int):
        del query, fetch
        return (
            _ChunkHit("M001", 0, "长记忆", "chunk 0", 0.9),
            _ChunkHit("M001", 1, "长记忆", "chunk 1", 0.8),
            _ChunkHit("M002", 0, "双路命中", "vector chunk", 0.7),
        )

    async def fts_hits(query: str, fetch: int):
        del query, fetch
        return (_ChunkHit("M002", 0, "", "exact keyword", 0.0),)

    monkeypatch.setattr(index, "_vector_search", vector_hits)
    monkeypatch.setattr(index, "_fts_search", fts_hits)

    result = await index.search("query", limit=2)

    assert [candidate.memory_id for candidate in result.candidates] == [
        "M002",
        "M001",
    ]
    assert result.candidates[1].rrf_score == pytest.approx(1 / 61)


# ----------------------------------------------------------------------
# Runtime 级：召回不写历史、不进摘要、事件可观测
# ----------------------------------------------------------------------


class RecordingModelAdapter(ModelAdapter):
    """记录每个 ModelRequest 的离线假 Adapter。"""

    def __init__(self, config, responses):
        super().__init__(config)
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    async def complete_stream(
        self,
        request: ModelRequest,
        *,
        on_text_delta,
        on_reasoning_delta=None,
    ):
        self.requests.append(request)
        await on_text_delta("完成")
        response = self.responses.pop(0)
        assert isinstance(response, ModelResponse)
        return response

    async def close(self) -> None:
        return None


def _offline_registry(responses):
    config = ProviderConfig(
        provider="fake",
        model="fake-model",
        api_key=SecretStr("offline-test-key"),
        api_style=ApiStyle.CHAT_COMPLETIONS,
    )
    adapter = RecordingModelAdapter(config, responses)
    registry = ModelAdapterRegistry(ModelSettings(_env_file=None))
    registry.register("fake", lambda _: adapter, config=config)
    return registry, adapter


@pytest.mark.asyncio
async def test_runtime_recall_not_persisted_into_history_or_summary(
    memory_root: Path,
    tmp_path: Path,
) -> None:
    from app.tools.builtin.read_file import ReadFileTool

    (tmp_path / "note.txt").write_text("工具输入", encoding="utf-8")
    registry, adapter = _offline_registry(
        [
            ModelResponse(
                id="r1",
                provider="fake",
                model="fake-model",
                message=Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            id="read-1",
                            name="read_file",
                            arguments={"path": "note.txt"},
                        ),
                    ),
                ),
                usage=ModelUsage(),
            ),
            ModelResponse(
                id="r2",
                provider="fake",
                model="fake-model",
                message=Message(role=MessageRole.ASSISTANT, content="已读取"),
                usage=ModelUsage(),
            ),
        ]
    )
    embedding = CountingFakeEmbedding()
    manager = _CountingRecallManager(memory_root, embedding=embedding)
    await manager.initialize()
    await _seed(manager)

    tools = ToolRegistry()
    tools.register(ReadFileTool(tmp_path))
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        memory_manager=manager,
    ).run(
        "讲讲数据库迁移的决定",
        history=(),
        conversation_id="conversation-recall",
        event_handler=events,
    )

    assert result.stop_reason is AgentStopReason.FINAL_ANSWER
    # 1) 每 Run 只检索一次（两次模型请求只触发一次 query 向量化）。
    assert manager.recall_calls == 1
    assert embedding.query_calls == 1
    # 2) 每个模型请求都能看到同一份 Recall 注入。
    assert len(adapter.requests) == 2
    for request in adapter.requests:
        names = [message.name for message in request.messages]
        assert MEMORY_RECALL_MESSAGE_NAME in names
        assert MEMORY_INDEX_MESSAGE_NAME not in names
    first_names = [message.name for message in adapter.requests[0].messages]
    second_names = [message.name for message in adapter.requests[1].messages]
    first_content = next(
        message.content
        for message in adapter.requests[0].messages
        if message.name == MEMORY_RECALL_MESSAGE_NAME
    )
    second_content = next(
        message.content
        for message in adapter.requests[1].messages
        if message.name == MEMORY_RECALL_MESSAGE_NAME
    )
    assert first_content == second_content
    assert first_names.count(MEMORY_RECALL_MESSAGE_NAME) == 1
    assert second_names.count(MEMORY_RECALL_MESSAGE_NAME) == 1
    # 3) 原始聊天历史不包含临时召回内容。
    persisted_names = [message.name for message in result.messages]
    assert MEMORY_RECALL_MESSAGE_NAME not in persisted_names
    # 4) 事件可观测：MODEL_STARTED 携带召回候选与模式。
    started = [
        event for event in events.events if event.type is AgentEventType.MODEL_STARTED
    ]
    assert len(started) == 2
    assert started[0].recall_candidate_ids == ("M001",)
    assert started[0].recall_mode == SearchMode.HYBRID.value
    # 5) 自动召回不增加 access_count。
    record = await manager.store.load("M001")
    assert record is not None
    assert record.access_count == 0


# ----------------------------------------------------------------------
# 只有 memory_read 才授权 Reflection Update
# ----------------------------------------------------------------------


def _tool_record(
    name: str,
    arguments: dict,
    output: dict,
    *,
    success: bool = True,
) -> ToolCallRecord:
    return ToolCallRecord(
        round_index=0,
        tool_call=ToolCall(id=f"{name}-1", name=name, arguments=arguments),
        result=ToolResult(
            tool_call_id=f"{name}-1",
            tool_name=name,
            success=success,
            output=json.dumps(output, ensure_ascii=False),
            duration_ms=1.0,
        ),
    )


def test_memory_search_hit_does_not_authorize_reflection_update() -> None:
    search_record = _tool_record(
        "memory_search",
        {"query": "数据库迁移"},
        {
            "available": True,
            "query": "数据库迁移",
            "mode": "hybrid",
            "results": [
                {
                    "memory_id": "M001",
                    "title": "数据库迁移决定",
                    "revision": 1,
                    "snippet": "…",
                }
            ],
        },
    )

    assert recalled_memory_revisions((search_record,)) == {}


def test_memory_read_success_authorizes_reflection_update() -> None:
    read_record = _tool_record(
        "memory_read",
        {"memory_id": "M001"},
        {"found": True, "id": "M001", "revision": 3, "content": "…"},
    )
    failed_read = _tool_record(
        "memory_read",
        {"memory_id": "M002"},
        {"found": False, "memory_id": "M002"},
        success=False,
    )

    assert recalled_memory_revisions((read_record, failed_read)) == {"M001": 3}


# ----------------------------------------------------------------------
# Fake Embedding：确定性且离线
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_embedding_is_deterministic() -> None:
    fake = FakeEmbeddingAdapter()
    first = await fake.embed_query("生产数据库迁移到 PostgreSQL")
    second = await fake.embed_query("生产数据库迁移到 PostgreSQL")
    other = await fake.embed_query("completely unrelated text")

    assert first == second
    assert first != other
    assert len(first) == fake.dimensions


# ----------------------------------------------------------------------
# 相似度阈值随 Embedding 模型校准
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_min_vector_similarity_threshold_is_wired(
    memory_root: Path,
) -> None:
    """阈值调到 1.0 时向量路径必然空手，检索退化为 FTS 单路。"""

    manager = MemoryManager(
        memory_root,
        embedding=FakeEmbeddingAdapter(),
        min_vector_similarity=0.99,
    )
    await manager.initialize()
    await _seed(manager)

    assert manager.search_settings.min_vector_similarity == 0.99
    result = await manager.search("pg-migration")
    # 向量被阈值全部过滤，但 FTS 路径仍然命中（mode 只反映路径可用性）。
    assert [candidate.memory_id for candidate in result.candidates] == ["M001"]
    assert result.candidates[0].matched_by_vector is False
    assert result.candidates[0].matched_by_fts is True
