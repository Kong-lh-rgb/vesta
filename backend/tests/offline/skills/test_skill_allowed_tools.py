"""Active Skill allowed-tools 收窄的离线测试（P0）。

覆盖：Schema 收窄、执行层硬拒绝（越权）、多 Skill 取交集、空交集、
未声明 Skill 的兼容语义、延迟工具、不能扩大 Plan Mode 白名单。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from app.agent.events import AgentEventType, InMemoryEventHandler
from app.agent.runtime import AgentRuntime
from app.models.adapter import ModelAdapter
from app.models.config import ModelSettings, ProviderConfig
from app.models.registry import ModelAdapterRegistry
from app.models.types import (
    AgentMode,
    ApiStyle,
    Message,
    MessageRole,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ToolCall,
)
from app.skills import (
    SKILL_READ_TOOL_NAME,
    SkillContextProvider,
    SkillStore,
    register_skill_tools,
)
from app.tools.base import BaseTool
from app.tools.builtin.read_file import ReadFileTool
from app.tools.builtin.write_file import WriteFileTool
from app.tools.registry import ToolRegistry


def _skill_md(name: str, allowed: str | None) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {name} 的测试 Skill",
    ]
    if allowed is not None:
        lines.append(f"allowed-tools: [{allowed}]")
    lines += ["---", "", f"# {name}", "", "测试指令正文。"]
    return "\n".join(lines) + "\n"


async def _store_with_skills(
    root: Path,
    skills: dict[str, str | None],
) -> SkillStore:
    project = root / "project-skills"
    for name, allowed in skills.items():
        skill_dir = project / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            _skill_md(name, allowed), encoding="utf-8"
        )
    store = SkillStore(root / "user-skills", project)
    await store.initialize()
    return store


class FakeModelAdapter(ModelAdapter):
    def __init__(
        self,
        config: ProviderConfig,
        responses: Sequence[ModelResponse | Exception],
    ) -> None:
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
        response = self.responses.pop(0)
        assert isinstance(response, ModelResponse)
        return response

    async def close(self) -> None:
        return None


def _response(**kwargs: Any) -> ModelResponse:
    return ModelResponse(
        id="fake-response",
        provider="fake",
        model="fake-model",
        message=Message(role=MessageRole.ASSISTANT, **kwargs),
        usage=ModelUsage(),
    )


def _fake_registry(
    responses: Sequence[ModelResponse | Exception],
) -> tuple[ModelAdapterRegistry, FakeModelAdapter]:
    config = ProviderConfig(
        provider="fake",
        model="fake-model",
        api_key=SecretStr("offline-test-key"),
        api_style=ApiStyle.CHAT_COMPLETIONS,
    )
    adapter = FakeModelAdapter(config, responses)
    registry = ModelAdapterRegistry(ModelSettings(_env_file=None))
    registry.register("fake", lambda _: adapter, config=config)
    return registry, adapter


def _tool_names(request: ModelRequest) -> set[str]:
    return {tool.name for tool in request.tools}


# ----------------------------------------------------------------------
# Registry 层：交集语义与不扩大
# ----------------------------------------------------------------------


def test_registry_scope_only_narrows() -> None:
    registry = ToolRegistry()
    registry.register(_stub_tool("read_file"))
    registry.register(_stub_tool("write_file"))

    normal = registry.allowed_names_for_mode(AgentMode.NORMAL)
    plan = registry.allowed_names_for_mode(AgentMode.PLAN)

    scoped = registry.allowed_names_for_mode(
        AgentMode.NORMAL, allowed_tools=frozenset({"read_file"})
    )
    # NORMAL 收窄为声明集合。
    assert scoped == frozenset({"read_file"})
    # Skill 声明不能扩大 Plan 白名单：write_file 仍被挡在 PLAN 之外。
    widened = registry.allowed_names_for_mode(
        AgentMode.PLAN, allowed_tools=frozenset({"read_file", "write_file"})
    )
    assert "write_file" in normal
    assert "write_file" not in plan
    assert "write_file" not in widened
    # 未声明（None）不约束。
    assert registry.allowed_names_for_mode(
        AgentMode.NORMAL, allowed_tools=None
    ) == normal


def test_registry_empty_scope_blocks_everything() -> None:
    registry = ToolRegistry()
    registry.register(_stub_tool("read_file"))

    definitions = registry.model_definitions_for_mode(
        AgentMode.NORMAL, allowed_tools=frozenset()
    )

    assert definitions == ()


def _stub_tool(name: str) -> BaseTool:
    class _Stub(BaseTool):
        def __init__(self) -> None:
            self._definition = type(
                "D", (), {}
            )()  # placeholder replaced below

        @property
        def definition(self):  # type: ignore[override]
            from app.models.types import ToolDefinition

            return ToolDefinition(
                name=name,
                description="stub",
                parameters={"type": "object", "properties": {}},
            )

        async def execute(self, arguments: dict[str, Any]) -> str:
            return "ok"

    return _Stub()


# ----------------------------------------------------------------------
# Runtime 层：激活后收窄 Schema + 越权硬拒绝
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_skill_narrows_schema_and_rejects_out_of_scope(
    tmp_path: Path,
) -> None:
    """Skill 声明只允许 read_file：write_file 从 Schema 消失且执行被拒。"""

    store = await _store_with_skills(
        tmp_path, {"research-readonly": "read_file"}
    )
    (tmp_path / "note.txt").write_text("内容", encoding="utf-8")
    registry, adapter = _fake_registry(
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="activate",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "research-readonly"},
                    ),
                )
            ),
            # 模型伪造调用 Schema 外的 write_file（越权）。
            _response(
                tool_calls=(
                    ToolCall(
                        id="forbidden-write",
                        name="write_file",
                        arguments={
                            "path": "evil.txt",
                            "content": "x",
                        },
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path))
    tools.register(WriteFileTool(tmp_path))
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "先激活 Skill 再尝试写文件",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    # 激活前：两个业务工具都可见。
    assert {"read_file", "write_file"} <= _tool_names(adapter.requests[0])
    # 激活后：write_file 从 Schema 消失，read_file 保留。
    step2_tools = _tool_names(adapter.requests[1])
    assert "read_file" in step2_tools
    assert "write_file" not in step2_tools
    # 越权调用被执行层硬拒绝，文件未被创建。
    completed = [
        event
        for event in events.events
        if event.type is AgentEventType.TOOL_COMPLETED
        and event.tool_result is not None
        and event.tool_result.tool_name == "write_file"
    ]
    assert completed
    assert completed[0].tool_result.success is False
    assert "allowed-tools" in (completed[0].tool_result.error or "")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.asyncio
async def test_multiple_skills_intersect(tmp_path: Path) -> None:
    """两个 Skill 同时声明：取交集（只剩 read_file）。"""

    store = await _store_with_skills(
        tmp_path,
        {
            "skill-a": "read_file, write_file",
            "skill-b": "read_file, list_files",
        },
    )
    (tmp_path / "note.txt").write_text("内容", encoding="utf-8")
    registry, adapter = _fake_registry(
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="a1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "skill-a"},
                    ),
                    ToolCall(
                        id="b1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "skill-b"},
                    ),
                )
            ),
            _response(
                tool_calls=(
                    ToolCall(
                        id="r1",
                        name="read_file",
                        arguments={"path": "note.txt"},
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path))
    tools.register(WriteFileTool(tmp_path))
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "激活两个 Skill 后读文件",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    step2_tools = _tool_names(adapter.requests[1])
    # 交集语义：只剩 read_file；write_file / list_files 均被收窄掉。
    assert step2_tools & {"read_file", "write_file", "list_files"} == {
        "read_file"
    }
    read_result = [
        event
        for event in events.events
        if event.type is AgentEventType.TOOL_COMPLETED
        and event.tool_result is not None
        and event.tool_result.tool_name == "read_file"
    ]
    assert read_result and read_result[0].tool_result.success is True


@pytest.mark.asyncio
async def test_disjoint_skills_produce_empty_scope(tmp_path: Path) -> None:
    """两个 Skill 声明不相交：空交集 = 无工具可用，任何调用被拒。"""

    store = await _store_with_skills(
        tmp_path,
        {"skill-x": "read_file", "skill-y": "write_file"},
    )
    registry, adapter = _fake_registry(
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="x1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "skill-x"},
                    ),
                    ToolCall(
                        id="y1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "skill-y"},
                    ),
                )
            ),
            # 模型仍尝试调用（空 Schema 下的伪造调用）。
            _response(
                tool_calls=(
                    ToolCall(
                        id="r1",
                        name="read_file",
                        arguments={"path": "note.txt"},
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path))
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "激活两个互斥 Skill",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    assert _tool_names(adapter.requests[1]) == set()
    rejected = [
        event
        for event in events.events
        if event.type is AgentEventType.TOOL_COMPLETED
        and event.tool_result is not None
        and event.tool_result.tool_name == "read_file"
    ]
    assert rejected
    assert rejected[0].tool_result.success is False


@pytest.mark.asyncio
async def test_skill_without_declaration_keeps_compatibility(
    tmp_path: Path,
) -> None:
    """未声明 allowed-tools 的旧 Skill：不收窄，全部工具可见。"""

    store = await _store_with_skills(tmp_path, {"legacy-skill": None})
    (tmp_path / "note.txt").write_text("内容", encoding="utf-8")
    registry, adapter = _fake_registry(
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="a1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "legacy-skill"},
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path))
    tools.register(WriteFileTool(tmp_path))
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "激活旧格式 Skill",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    step2_tools = _tool_names(adapter.requests[1])
    assert {"read_file", "write_file"} <= step2_tools


@pytest.mark.asyncio
async def test_deferred_tool_in_scope_usable_after_activation(
    tmp_path: Path,
) -> None:
    """范围内的延迟工具：tool_search 激活后可见可用。"""

    from app.tools.catalog import TOOL_SEARCH_NAME

    store = await _store_with_skills(
        tmp_path, {"defer-scope": "read_file, tool_search"}
    )
    (tmp_path / "note.txt").write_text("内容", encoding="utf-8")
    registry, adapter = _fake_registry(
        [
            # 收窄生效前：激活 Skill + 检索激活延迟工具。
            _response(
                tool_calls=(
                    ToolCall(
                        id="a1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "defer-scope"},
                    ),
                    ToolCall(
                        id="s1",
                        name=TOOL_SEARCH_NAME,
                        arguments={"query": "read_file"},
                    ),
                )
            ),
            _response(
                tool_calls=(
                    ToolCall(
                        id="r1",
                        name="read_file",
                        arguments={"path": "note.txt"},
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path), deferred=True)
    tools.register(WriteFileTool(tmp_path), deferred=True)
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "激活 Skill 并用延迟工具读文件",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    # 收窄 + 激活后：read_file 可见；未激活的 write_file 不可见。
    step2_tools = _tool_names(adapter.requests[1])
    assert "read_file" in step2_tools
    assert "write_file" not in step2_tools
    reads = [
        event
        for event in events.events
        if event.type is AgentEventType.TOOL_COMPLETED
        and event.tool_result is not None
        and event.tool_result.tool_name == "read_file"
    ]
    assert reads and reads[0].tool_result.success is True


@pytest.mark.asyncio
async def test_tool_search_outside_scope_is_rejected(tmp_path: Path) -> None:
    """范围不含 tool_search：激活入口本身也被收窄拒绝（严格交集语义）。"""

    from app.tools.catalog import TOOL_SEARCH_NAME

    store = await _store_with_skills(tmp_path, {"narrow-scope": "read_file"})
    registry, adapter = _fake_registry(
        [
            _response(
                tool_calls=(
                    ToolCall(
                        id="a1",
                        name=SKILL_READ_TOOL_NAME,
                        arguments={"name": "narrow-scope"},
                    ),
                )
            ),
            _response(
                tool_calls=(
                    ToolCall(
                        id="s1",
                        name=TOOL_SEARCH_NAME,
                        arguments={"query": "write_file"},
                    ),
                )
            ),
            _response(content="完成"),
        ]
    )
    tools = ToolRegistry()
    register_skill_tools(tools, store)
    tools.register(ReadFileTool(tmp_path), deferred=True)
    tools.register(WriteFileTool(tmp_path), deferred=True)
    events = InMemoryEventHandler()

    result = await AgentRuntime(
        registry,
        tools,
        provider="fake",
        skill_store=store,
        skill_context_provider=SkillContextProvider(
            max_tokens=4_096, max_active=4
        ),
    ).run(
        "激活只允许 read_file 的 Skill",
        history=(),
        event_handler=events,
    )

    assert result.ok is True
    searches = [
        event
        for event in events.events
        if event.type is AgentEventType.TOOL_COMPLETED
        and event.tool_result is not None
        and event.tool_result.tool_name == TOOL_SEARCH_NAME
    ]
    assert searches
    assert searches[0].tool_result.success is False
    assert "allowed-tools" in (searches[0].tool_result.error or "")
