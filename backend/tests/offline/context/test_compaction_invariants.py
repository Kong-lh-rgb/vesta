"""上下文压缩不变量验证（P1-10）。

逐条验证压缩链路的产品级不变量：
1. 最近两个工具轮不被第一层清理截断（已有单元覆盖，此处端到端复核）；
2. Tool Call 与 Tool Result 永不拆散；
3. 压缩后 Task / Core Memory / Active Skill 系统状态全部重新注入；
4. 被清理的工具原文可通过 evidence_read 找回；
5. 被摘要的旧聊天可通过 conversation store（history 工具的数据源）找回。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.agent.events import AgentEventType, InMemoryEventHandler
from app.agent.runtime import AgentRuntime
from app.context import ContextManager
from app.context.reducers import ToolReducer
from app.evidence import EvidenceRecorder, SQLiteEvidenceStore
from app.memory import (
    MemoryManager,
    register_memory_tools,
)
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
    ToolDefinition,
)
from app.skills import (
    ACTIVE_SKILL_MESSAGE_NAME,
    SKILL_READ_TOOL_NAME,
    SkillContextProvider,
    SkillStore,
    register_skill_tools,
)
from app.task import (
    TASK_CONTEXT_MESSAGE_NAME,
    FileTaskStore,
    TaskContextProvider,
    TaskStep,
    register_task_tools,
)
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry

# ----------------------------------------------------------------------
# 纯逻辑：最近两轮保护 / 协议不拆散（快速回归）
# ----------------------------------------------------------------------


def _tool_round(call_id: str, name: str, output: str) -> tuple[Message, ...]:
    return (
        Message(
            role=MessageRole.ASSISTANT,
            tool_calls=(ToolCall(id=call_id, name=name, arguments={}),),
        ),
        Message(role=MessageRole.TOOL, tool_call_id=call_id, content=output),
    )


def _conversation_turn(user: str, assistant: str) -> tuple[Message, ...]:
    return (
        Message(role=MessageRole.USER, content=user),
        Message(role=MessageRole.ASSISTANT, content=assistant),
    )


def _estimate(messages: Sequence[Message]) -> int:
    return sum(len(message.content or "") + 16 for message in messages)


def test_recent_two_rounds_survive_first_layer_cleanup() -> None:
    """预算极小时也只截短更旧结果，最近两轮保持完整。"""

    messages = (
        _tool_round("old-1", "read_file", "A" * 800)
        + _tool_round("recent-1", "read_file", "C" * 400)
        + _tool_round("recent-2", "read_file", "D" * 400)
    )
    reducer = ToolReducer(
        keep_recent_tool_rounds=2,
        max_tool_result_chars=400,
        tool_result_head_chars=80,
        tool_result_tail_chars=60,
    )
    result = reducer.project(
        messages,
        tool_result_budget_tokens=1_200,  # 截短可满足，不触发整轮移除
        estimate_request=_estimate,
        estimate_tool_results=_estimate,
    )

    contents = {
        message.tool_call_id: message.content or ""
        for message in result.messages
        if message.role is MessageRole.TOOL
    }
    # 最近两轮原样保留；旧轮被截短（内容变短但仍非空）。
    assert contents["recent-1"] == "C" * 400
    assert contents["recent-2"] == "D" * 400
    assert 0 < len(contents["old-1"]) < 400


def test_tool_protocol_pairs_never_split_during_cleanup() -> None:
    """清理后每个 tool_call 都有配对的 tool result，协议完整。"""

    messages = (
        _conversation_turn("开始", "好的")
        + _tool_round("r1", "read_file", "X" * 600)
        + _tool_round("r2", "read_file", "Y" * 600)
        + (Message(role=MessageRole.USER, content="继续"),)
    )
    reducer = ToolReducer(
        keep_recent_tool_rounds=2,
        max_tool_result_chars=300,
        tool_result_head_chars=80,
        tool_result_tail_chars=60,
    )
    result = reducer.project(
        messages,
        tool_result_budget_tokens=5,
        estimate_request=_estimate,
        estimate_tool_results=_estimate,
    )

    call_ids = {
        call.id
        for message in result.messages
        for call in message.tool_calls
    }
    result_ids = {
        message.tool_call_id
        for message in result.messages
        if message.role is MessageRole.TOOL
    }
    assert call_ids == result_ids  # 调用与结果一一配对


# ----------------------------------------------------------------------
# 端到端：压缩后系统状态重新注入 + 原文可找回
# ----------------------------------------------------------------------


class RecordingAdapter(ModelAdapter):
    def __init__(self, config: ProviderConfig, responses: list[ModelResponse]):
        super().__init__(config)
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError

    async def complete_stream(
        self,
        request: ModelRequest,
        *,
        on_text_delta: Callable[[str], Awaitable[None]],
        on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelResponse:
        self.requests.append(request)
        await on_text_delta("完成")
        return self.responses.pop(0)

    async def close(self) -> None:
        return None


def _response(**kwargs) -> ModelResponse:
    return ModelResponse(
        id="resp",
        provider="fake",
        model="fake-model",
        message=Message(role=MessageRole.ASSISTANT, **kwargs),
        usage=ModelUsage(),
    )


class HeavyEchoTool(BaseTool):
    """返回超长输出，制造工具结果压缩压力并留下 evidence_id。"""

    def __init__(self, payload: str) -> None:
        self._payload = payload
        self._definition = ToolDefinition(
            name="heavy_echo",
            description="返回长文本",
            parameters={"type": "object", "properties": {}},
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, arguments: dict[str, object]) -> str:
        return self._payload


@pytest.mark.asyncio
async def test_system_states_reinject_after_compaction(tmp_path: Path) -> None:
    """滚动摘要压缩后，Task / Core Memory / Active Skill 仍全部注入。"""

    # 三个系统状态源。
    task_store = FileTaskStore(tmp_path / "tasks")
    await task_store.initialize()
    task = await task_store.create(
        title="压缩后的任务",
        steps=(TaskStep(id="step-1", title="继续执行"),),
        owner_conversation_id="conversation-inv",
    )
    await task_store.plan_accept(task.id)

    memory_manager = MemoryManager(tmp_path / "memory")
    await memory_manager.initialize()

    skill_dir = tmp_path / "project-skills" / "compaction-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: compaction-skill\ndescription: 压缩测试技能\n---\n\n正文",
        encoding="utf-8",
    )
    skill_store = SkillStore(tmp_path / "user-skills", tmp_path / "project-skills")
    await skill_store.initialize()

    # 大量历史 + 两轮长工具结果，保证越过压缩线触发滚动摘要。
    history: list[Message] = []
    for index in range(10):
        history.extend(
            _conversation_turn(
                f"历史问题 {index} " + "细节" * 60,
                f"历史回答 {index} " + "结论" * 60,
            )
        )

    config = ProviderConfig(
        provider="fake",
        model="fake-model",
        api_key=SecretStr("offline-key"),
        api_style=ApiStyle.CHAT_COMPLETIONS,
    )
    adapter = RecordingAdapter(
        config,
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="activate-skill",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "compaction-skill"},
                    ),
                )
            ),
            _response(content="最终回答"),
        ],
    )
    registry = ModelAdapterRegistry(ModelSettings(_env_file=None))
    registry.register("fake", lambda _: adapter, config=config)

    tools = ToolRegistry()
    register_skill_tools(tools, skill_store)
    register_memory_tools(tools, memory_manager)
    register_task_tools(tools, task_store)

    context_manager = ContextManager(
        budget_policy=_tiny_budget_policy(),
        conversation_reducer=_summary_reducer(),
    )
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        context_manager=context_manager,
        task_context_provider=TaskContextProvider(task_store),
        memory_manager=memory_manager,
        skill_store=skill_store,
        skill_context_provider=SkillContextProvider(max_tokens=4_096, max_active=4),
    ).run(
        "激活技能后继续",
        history=tuple(history),
        conversation_id="conversation-inv",
        event_handler=events,
    )

    assert result.ok is True
    # 压缩确实发生（滚动摘要写入）。
    summary_events = [
        event
        for event in events.events
        if event.type is AgentEventType.MODEL_STARTED
        and event.summary_updated
    ]
    assert summary_events, "应至少发生一次滚动摘要"
    # 压缩后的最后一个请求同时包含三类系统状态。
    final_request = adapter.requests[-1]
    names = {message.name for message in final_request.messages}
    assert TASK_CONTEXT_MESSAGE_NAME in names
    assert ACTIVE_SKILL_MESSAGE_NAME in names
    # Core Memory 为空时不注入（无内容）；Policy 属于 Memory 注入组。
    assert any(
        message.name and message.name.startswith("vesta_memory")
        for message in final_request.messages
    )


def _tiny_budget_policy():
    from app.context import ContextBudgetPolicy

    return ContextBudgetPolicy(
        safety_margin_tokens=100,
        preferred_input_tokens=2_000,
        working_trigger_ratio=0.5,
        working_target_ratio=0.3,
    )


def _summary_reducer():
    from app.context import (
        ContextSummarizer,
        ConversationReducer,
        SummaryGenerationResult,
    )
    from app.context.summary import RollingConversationSummary

    class FixedSummarizer(ContextSummarizer):
        async def summarize(
            self, previous_summary, messages, *, max_output_tokens=None
        ):
            return SummaryGenerationResult(
                summary=RollingConversationSummary(current_objective="压缩后继续"),
                usage=ModelUsage(input_tokens=5, output_tokens=2, total_tokens=7),
            )

    return ConversationReducer(FixedSummarizer(), keep_recent_conversation_blocks=2)


@pytest.mark.asyncio
async def test_evicted_tool_output_recoverable_via_evidence(tmp_path: Path) -> None:
    """工具原文被压缩截断后，evidence_read 仍可取回完整原文。"""

    from app.tools.executor import ToolExecutor
    from app.tools.hooks import ToolExecutionContext

    database = tmp_path / "vesta.db"
    evidence_store = SQLiteEvidenceStore(database)
    await evidence_store.initialize()
    long_output = "重要原始输出 " + "细节内容" * 6_000

    # 全链路：executor 先把完整原文归档进 Evidence，再给模型有界预览。
    registry = ToolRegistry()
    registry.register(HeavyEchoTool(long_output))
    executor = ToolExecutor(
        registry, output_recorder=EvidenceRecorder(evidence_store)
    )
    call = ToolCall(id="call-evict", name="heavy_echo", arguments={})
    result = await executor.execute(
        call,
        context=ToolExecutionContext(
            tool_call=call,
            run_id="run-evict",
            conversation_id="conversation-evict",
        ),
    )

    assert result.success is True
    assert result.evidence_id is not None
    # 模型只看到截断预览（长度远小于原文）。
    assert len(result.output or "") < len(long_output)

    # 通过 evidence store（evidence_read 的数据源）找回完整原文。
    document = await evidence_store.resolve(
        result.evidence_id, conversation_id="conversation-evict"
    )
    assert document is not None
    assert document.content == long_output


@pytest.mark.asyncio
async def test_summarized_chat_recoverable_from_conversation_store(
    tmp_path: Path,
) -> None:
    """旧聊天被滚动摘要替换后，原始消息仍完整保存在 Conversation Store。"""

    from app.conversation import SQLiteConversationStore

    store = SQLiteConversationStore(tmp_path / "vesta.db")
    await store.initialize()
    original = list(
        _conversation_turn("早期的重要决定", "决定采用两级压缩阈值方案。")
        + _conversation_turn("继续讨论", "确认 defer 上限为两步。")
    )

    conversation = await store.create(messages=tuple(original))

    # 摘要只改变模型请求视图；history 工具读取的持久源不受影响。
    persisted = await store.load_messages(conversation.id)

    assert [m.content for m in persisted] == [m.content for m in original]
    # history_search（同一数据源）能命中被摘要覆盖的关键词。
    hits = await store.search_messages(conversation.id, "两级压缩阈值")
    assert hits and "两级压缩阈值" in (hits[0].message.content or "")
