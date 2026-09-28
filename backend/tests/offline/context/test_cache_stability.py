"""Prompt Cache 稳定性回归（P1-11）。

验证缓存前缀友好的三个结构不变量：
1. 工具定义按名称稳定排序（同一注册集合的 Schema 顺序跨调用确定）；
2. 注册顺序不影响导出顺序（前缀字节稳定）；
3. 固定多步场景重跑：缓存复用判定序列一致（确定性，可作基线观测，
   不宣称跨样本严格 A/B）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pydantic import SecretStr

from app.agent.events import AgentEventType, InMemoryEventHandler
from app.agent.runtime import AgentRuntime
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
from app.tools.base import BaseTool
from app.tools.builtin.read_file import ReadFileTool
from app.tools.builtin.write_file import WriteFileTool
from app.tools.registry import ToolRegistry


def _stub(name: str) -> BaseTool:
    class _Stub(BaseTool):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name=name,
                description=f"stub {name}",
                parameters={"type": "object", "properties": {}},
            )

        async def execute(self, arguments: dict[str, Any]) -> str:
            return "ok"

    return _Stub()


def test_tool_definitions_sorted_by_name_across_registrations() -> None:
    """同一注册集合按名称稳定排序；注册顺序不影响导出。"""

    names = ["zeta_tool", "alpha_tool", "middle_tool", "beta_2", "beta_10"]

    forward = ToolRegistry()
    for name in names:
        forward.register(_stub(name))
    backward = ToolRegistry()
    for name in reversed(names):
        backward.register(_stub(name))

    forward_order = [d.name for d in forward.model_definitions()]
    backward_order = [d.name for d in backward.model_definitions()]

    assert forward_order == sorted(names)
    assert backward_order == sorted(names)
    # Schema 字节顺序稳定：两次导出的 JSON 序列化一致（前缀缓存友好）。
    assert [d.model_dump_json() for d in forward.model_definitions()] == [
        d.model_dump_json() for d in backward.model_definitions()
    ]


class _CacheRecordingAdapter(ModelAdapter):
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


def _fixed_scenario(
    tmp_path, responses_factory: Callable[[], list[ModelResponse]]
):
    """固定三步场景：读文件 → 写文件 → 最终回答。"""

    (tmp_path / "note.txt").write_text("内容", encoding="utf-8")
    config = ProviderConfig(
        provider="fake",
        model="fake-model",
        api_key=SecretStr("offline-key"),
        api_style=ApiStyle.CHAT_COMPLETIONS,
    )
    adapter = _CacheRecordingAdapter(config, responses_factory())
    registry = ModelAdapterRegistry(ModelSettings(_env_file=None))
    registry.register("fake", lambda _: adapter, config=config)
    tools = ToolRegistry()
    tools.register(ReadFileTool(tmp_path))
    tools.register(WriteFileTool(tmp_path))
    runtime = AgentRuntime(registry, tools, provider="fake")
    return runtime, adapter


def _scenario_responses() -> list[ModelResponse]:
    def _resp(**kwargs) -> ModelResponse:
        return ModelResponse(
            id="resp",
            provider="fake",
            model="fake-model",
            message=Message(role=MessageRole.ASSISTANT, **kwargs),
            usage=ModelUsage(),
        )

    return [
        _resp(
            tool_calls=(
                ToolCall(id="c1", name="read_file", arguments={"path": "note.txt"}),
            )
        ),
        _resp(
            tool_calls=(
                ToolCall(
                    id="c2",
                    name="write_file",
                    arguments={"path": "out.txt", "content": "结果"},
                ),
            )
        ),
        _resp(content="完成"),
    ]


@pytest.mark.asyncio
async def test_fixed_scenario_reruns_produce_identical_cache_decisions(
    tmp_path,
) -> None:
    """固定场景重跑：每步的缓存复用判定与工具集合序列完全一致。

    这是确定性基线观测（同场景重跑），不用于跨样本 A/B 对比。
    """

    decisions_runs: list[list[tuple[bool, int]]] = []
    tool_names_runs: list[list[tuple[str, ...]]] = []

    for round_index in range(2):
        base = tmp_path / f"round-{round_index}"
        base.mkdir()
        runtime, adapter = _fixed_scenario(base, _scenario_responses)
        events = InMemoryEventHandler()
        result = await runtime.run(
            "读取并写入", history=(), event_handler=events
        )
        assert result.ok is True
        started = [
            event
            for event in events.events
            if event.type is AgentEventType.MODEL_STARTED
        ]
        decisions_runs.append(
            [
                (event.cache_prefix_reused is True, event.cache_prefix_message_count)
                for event in started
            ]
        )
        tool_names_runs.append(
            [tuple(tool.name for tool in request.tools) for request in adapter.requests]
        )

    first, second = decisions_runs
    assert first == second, "同场景重跑的缓存复用判定必须确定"
    assert tool_names_runs[0] == tool_names_runs[1], "工具 Schema 序列必须确定"
    # 三步场景的结构断言：首步无前缀可复用，后两步追加复用。
    assert first[0][0] is False
    assert first[1][0] is True and first[1][1] > 0
    assert first[2][0] is True and first[2][1] > 0
    # 工具集合在无激活事件时保持不变（延迟工具未激活不改 Schema）。
    assert tool_names_runs[0][0] == tool_names_runs[0][1] == tool_names_runs[0][2]
