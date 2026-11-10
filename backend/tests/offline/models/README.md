# OpenAI-compatible endpoints: configuration and offline checks

Vesta can use a custom Chat Completions endpoint through its existing `openai`
provider. In your local `backend/.env`, set:

```dotenv
MODEL_DEFAULT_PROVIDER=openai
OPENAI_API_KEY=replace-with-your-private-key
OPENAI_BASE_URL=https://your-provider.example/v1
OPENAI_MODEL=replace-with-a-model-supported-by-your-endpoint
OPENAI_API_STYLE=chat_completions
```

Use the provider's documented API base URL and model identifier. Keep real keys
out of commits, fixtures, screenshots, and issue comments. Process environment
variables override `.env`. Explicitly select `chat_completions`: the `openai`
provider defaults to `responses`, which requires a different endpoint and event
format. This example does not establish compatibility with any particular service.

## Community-tested endpoints

The following is a dated community report, not an official Vesta endorsement or
a guarantee of compatibility with every model or feature. Results were reported
by A2Agent using Vesta's existing `openai` provider and actual
`OpenAICompatibleAdapter`; no provider-specific integration is required.

### A2Agent — reported verification on 2026-11-09

| Setting | Tested value |
| --- | --- |
| Service | [A2Agent](https://a2agent.me/) |
| Base URL | `https://api.a2agent.me/v1` |
| Model | `deepseek-v4-flash` |
| API styles (tested separately) | `chat_completions`, `responses` |
| Vesta revision | `cebc3ab867d3ceaadde37660d5884c496832ef47` |
| Test environment | Windows amd64; Python 3.14.2, OpenAI SDK 2.50.0, httpx 0.28.1 |

Select the desired API style explicitly using `OPENAI_API_STYLE` in the local
configuration above, with this base URL and model. Supply your own private API
key; do not commit it.

| Live check | Chat Completions | Responses |
| --- | --- | --- |
| Non-streaming text with expected marker | Passed | Passed |
| Streamed text and final result | Passed (`stop`) | Passed (`completed`) |
| Streamed `compat_echo` call with valid ID and JSON arguments | Passed | Passed |
| Fixed local tool-result continuation to expected final marker | Passed | Passed |
| Invalid-key error propagated through `ModelAdapterError` | Passed (HTTP 401) | Passed (HTTP 401) |

Authenticated model discovery also returned 22 models, including the tested
model. These results are A2Agent's self-reported live checks at the listed date
and revision. The tests exercised the adapter/SDK round trip with a fixed local
tool result, not the full desktop workflow or arbitrary shell tools. Other
models and features were not verified; live HTTP 429 responses and deliberate
network interruptions were not tested. Offline synthetic fixtures below are
separate from these live results.

See the [reported results and sanitized trace summary](https://github.com/Kong-lh-rgb/vesta/issues/4#issuecomment-6731574814)
and the [maintainer's documentation scope](https://github.com/Kong-lh-rgb/vesta/issues/4#issuecomment-6733105168).

## Run without credentials or network access

From `backend`, after installing `requirements-dev.txt`:

```bash
python -m pytest tests/offline/models/test_openai_wire_compatibility.py -q
```

These synthetic SSE fixtures pass through the pinned OpenAI SDK and Vesta's
adapter using `httpx.MockTransport`. No sockets, live API requests, provider
accounts, or new dependencies are needed. Bytes are delivered one at a time,
including across UTF-8 and CRLF boundaries. Checks cover text completion,
fragmented Chat Completions tool calls and tool-result continuation, HTTP
401/429 errors, and transport interruption after visible text without replay.

## Stream termination: current behavior, not a proposed change

The characterization tests record the existing behavior of the two API styles:

| Fixture ending after a text delta | Chat Completions | Responses |
| --- | --- | --- |
| Normal protocol completion | Text returned; `finish_reason=stop` | Final response returned; `finish_reason=completed` |
| `[DONE]` only | Text returned; `stop` inferred | `ModelAdapterError`: missing `response.completed` |
| Clean transport EOF only | Text returned; `stop` inferred | `ModelAdapterError`: missing `response.completed` |
| Chat `finish_reason=stop`, no `[DONE]` | Text returned | Not a Responses event format |

For a minimal Chat Completions reproduction, send this SSE event, then close the
body cleanly, without a finish-reason chunk or `[DONE]`:

```text
data: {"id":"chat_fixture","object":"chat.completion.chunk","created":0,"model":"fixture-model","choices":[{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}

```

The adapter currently returns `hello` and infers `stop`. For the matching
Responses reproduction, send this event, then close cleanly without a
`response.completed` event:

```text
data: {"type":"response.output_text.delta","delta":"hello","item_id":"msg_fixture","output_index":0,"content_index":0,"sequence_number":0}

```

The adapter delivers the visible delta, then raises `ModelAdapterError` containing
`response stream ended without response.completed`. A `[DONE]` sentinel alone
does not replace `response.completed` in this path. The SDK consumes the sentinel;
the adapter sees iterator termination.

A clean EOF differs from an explicit transport exception. The interruption
fixtures raise `httpx.ReadError` after a visible delta: both API styles surface
`ModelAdapterError` and do not retry already-delivered text, even with two adapter
retries configured. The HTTP error fixtures disable SDK retries for deterministic
checks; they do not change Vesta's production retry settings.

These cases characterize Vesta and SDK behavior using synthetic responses. They
are not evidence that a particular provider emits truncated streams, and do not
validate a live provider. Whether to require explicit Chat Completions termination
is a separate implementation decision; these tests do not change that policy.
