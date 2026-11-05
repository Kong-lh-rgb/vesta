"""Offline wire fixtures through the real SDK; no provider credentials or sockets."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from openai import APIStatusError, AsyncOpenAI
from pydantic import SecretStr

from app.models import (
    ApiStyle,
    Message,
    MessageRole,
    ModelAdapterError,
    ModelRequest,
    ProviderConfig,
    ToolDefinition,
)
from app.models.providers.openai_compatible import OpenAICompatibleAdapter


class WireStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes, *, fail: bool = False) -> None:
        self.body = body
        self.fail = fail

    async def __aiter__(self) -> AsyncIterator[bytes]:
        # Split even UTF-8 and SSE boundaries to exercise the SDK's decoder.
        for byte in self.body:
            yield bytes([byte])
        if self.fail:
            raise httpx.ReadError("fixture connection interrupted")


def event(value: dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\r\n\r\n").encode()


def chat(delta: dict[str, Any], finish: str | None = None) -> bytes:
    return event(
        {
            "id": "chat_fixture",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "fixture-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
    )


def text_event(style: ApiStyle) -> bytes:
    if style is ApiStyle.CHAT_COMPLETIONS:
        return chat({"content": "你好"})
    return event(
        {
            "type": "response.output_text.delta",
            "delta": "你好",
            "item_id": "msg_fixture",
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 0,
        }
    )


def completed() -> bytes:
    return event(
        {
            "type": "response.completed",
            "sequence_number": 1,
            "response": {
                "id": "resp_fixture",
                "object": "response",
                "created_at": 0,
                "model": "fixture-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_fixture",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "你好",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        }
    )


def make_adapter(
    style: ApiStyle,
    handler: Any,
    *,
    retries: int = 0,
) -> OpenAICompatibleAdapter:
    client = AsyncOpenAI(
        api_key="offline-placeholder",
        base_url="https://fixture.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ),
    )
    return OpenAICompatibleAdapter(
        ProviderConfig(
            provider="openai",
            model="fixture-model",
            api_style=style,
            api_key=SecretStr("offline-placeholder"),
            max_retries=retries,
        ),
        client=client,
    )


def request() -> ModelRequest:
    return ModelRequest(messages=(Message(role=MessageRole.USER, content="hello"),))


@pytest.mark.parametrize("ending", ["complete", "finish_only", "done_only", "eof"])
async def test_chat_termination_characterization(ending: str) -> None:
    body = text_event(ApiStyle.CHAT_COMPLETIONS)
    if ending in {"complete", "finish_only"}:
        body += chat({}, "stop")
    if ending in {"complete", "done_only"}:
        body += b"data: [DONE]\r\n\r\n"
    adapter = make_adapter(
        ApiStyle.CHAT_COMPLETIONS,
        lambda _: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=WireStream(body),
        ),
    )
    deltas: list[str] = []

    async def collect(delta: str) -> None:
        deltas.append(delta)

    try:
        result = await adapter.complete_stream(request(), on_text_delta=collect)
        # Characterize the existing permissive EOF behavior, not a new contract.
        assert result.message.content == "你好"
        assert result.finish_reason == "stop"
        assert deltas == ["你好"]
    finally:
        await adapter.close()


@pytest.mark.parametrize("ending", ["complete", "done_only", "eof"])
async def test_responses_termination_characterization(ending: str) -> None:
    body = text_event(ApiStyle.RESPONSES)
    if ending == "complete":
        body += completed()
    elif ending == "done_only":
        body += b"data: [DONE]\r\n\r\n"
    adapter = make_adapter(
        ApiStyle.RESPONSES,
        lambda _: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=WireStream(body),
        ),
    )
    deltas: list[str] = []

    async def collect(delta: str) -> None:
        deltas.append(delta)

    try:
        if ending == "complete":
            result = await adapter.complete_stream(request(), on_text_delta=collect)
            assert result.message.content == "你好"
            assert result.finish_reason == "completed"
        else:
            with pytest.raises(ModelAdapterError, match="without response.completed"):
                await adapter.complete_stream(request(), on_text_delta=collect)
        assert deltas == ["你好"]
    finally:
        await adapter.close()


@pytest.mark.parametrize("style", list((ApiStyle.CHAT_COMPLETIONS, ApiStyle.RESPONSES)))
async def test_transport_failure_after_text_is_not_replayed(style: ApiStyle) -> None:
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=WireStream(text_event(style), fail=True),
        )

    adapter = make_adapter(style, handler, retries=2)
    deltas: list[str] = []

    async def collect(delta: str) -> None:
        deltas.append(delta)

    try:
        with pytest.raises(ModelAdapterError, match="fixture connection interrupted"):
            await adapter.complete_stream(request(), on_text_delta=collect)
        assert deltas == ["你好"]
        assert len(requests) == 1
    finally:
        await adapter.close()


@pytest.mark.parametrize("style", [ApiStyle.CHAT_COMPLETIONS, ApiStyle.RESPONSES])
@pytest.mark.parametrize("status", [401, 429])
async def test_http_error_keeps_sdk_cause(style: ApiStyle, status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": "offline fixture error",
                    "type": "fixture_error",
                }
            },
        )

    adapter = make_adapter(style, handler)
    deltas: list[str] = []

    async def collect(delta: str) -> None:
        deltas.append(delta)

    try:
        with pytest.raises(ModelAdapterError) as caught:
            await adapter.complete_stream(request(), on_text_delta=collect)
        assert isinstance(caught.value.__cause__, APIStatusError)
        assert caught.value.__cause__.status_code == status
        assert deltas == []
        assert len(requests) == 1
    finally:
        await adapter.close()


async def test_chat_streamed_tool_result_continuation() -> None:
    sent: list[dict[str, Any]] = []
    body = (
        chat(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_fixture",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"city":'},
                    }
                ]
            }
        )
        + chat(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": '"北京"}'},
                    }
                ]
            },
            "tool_calls",
        )
        + b"data: [DONE]\r\n\r\n"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        if len(sent) == 1:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=WireStream(body),
            )
        return httpx.Response(
            200,
            json={
                "id": "chat_final",
                "object": "chat.completion",
                "created": 0,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "found"},
                    }
                ],
            },
        )

    adapter = make_adapter(ApiStyle.CHAT_COMPLETIONS, handler)

    async def no_text(delta: str) -> None:
        pytest.fail(f"tool-only stream unexpectedly emitted text: {delta!r}")

    try:
        first = await adapter.complete_stream(
            ModelRequest(
                messages=request().messages,
                tools=(ToolDefinition(name="lookup"),),
            ),
            on_text_delta=no_text,
        )
        (call,) = first.message.tool_calls
        assert call.id == "call_fixture"
        assert call.name == "lookup"
        assert call.arguments == {"city": "北京"}
        assert first.finish_reason == "tool_calls"
        final = await adapter.complete(
            ModelRequest(
                messages=(
                    *request().messages,
                    first.message,
                    Message(
                        role=MessageRole.TOOL, tool_call_id=call.id, content="record"
                    ),
                )
            )
        )
        assert final.message.content == "found"
        history = sent[1]["messages"]
        assert history[1]["tool_calls"][0]["id"] == call.id
        assert json.loads(history[1]["tool_calls"][0]["function"]["arguments"]) == {
            "city": "北京",
        }
        assert history[2] == {
            "role": "tool",
            "tool_call_id": call.id,
            "content": "record",
        }
        assert sent[0]["stream_options"] == {"include_usage": True}
    finally:
        await adapter.close()
