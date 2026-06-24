"""OpenAIBackend — OpenAI chat models via the official `openai` Python SDK.

This is the compliant, BYO-metered-key path (Config.openai_api_key): a shared
multi-user bot must NOT reuse subscription / coding-plan tokens (see config.py).
This mirrors the structure of `claude_api.py` (ClaudeApiBackend) — same seam,
different vendor.

We use the async streaming Chat Completions API: ``await
client.chat.completions.create(..., stream=True, stream_options={"include_usage":
True})`` returns an async stream of chunks. Each chunk carries an incremental
text delta at ``chunk.choices[0].delta.content``; streaming avoids request
timeouts on long inputs/outputs and lets the chat surface show progress. The
``stream_options={"include_usage": True}`` flag asks the API to emit one extra
final chunk whose ``.usage`` holds whole-request token counts
(``prompt_tokens`` / ``completion_tokens``); on all earlier chunks ``.usage`` is
None. That final usage feeds ``report_usage()``.

We chose Chat Completions (not the newer Responses API ``client.responses.stream``)
because it is the stable, broadly-supported surface and maps 1:1 onto the
TurnRequest contract (a system message + role/content messages), keeping this
backend symmetric with the Anthropic one.

The `openai` import is at module top level on purpose: the registry
(backends/registry.py) imports this module lazily and converts a missing SDK into
a friendly "pip install 'agent-tag[openai]'" error, so the core still runs
without the SDK installed.

SDK reference (verified 2026-06-24, openai >= 1.x):
https://github.com/openai/openai-python  (§Async usage, §Streaming responses)
  - from openai import AsyncOpenAI; AsyncOpenAI(api_key=...)
  - stream = await client.chat.completions.create(
        model=, messages=, stream=True, stream_options={"include_usage": True})
    async for chunk in stream: chunk.choices[0].delta.content / chunk.usage
Usage stats while streaming:
https://community.openai.com/t/usage-stats-now-available-when-using-streaming-with-the-chat-completions-api-or-completions-api/738156
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import openai  # top-level: registry catches ImportError; core runs without the SDK

from agent_tag.backends.base import BackendAdapter, Delta, TurnRequest, Usage

# Default when neither the request nor Config pins a model.
DEFAULT_MODEL = "gpt-5.5"


class OpenAIBackend(BackendAdapter):
    name = "openai"

    def __init__(self, config) -> None:
        self.config = config
        # AsyncOpenAI also reads OPENAI_API_KEY from the env, but we pass the
        # value off Config explicitly so the configured key is authoritative.
        self._client = openai.AsyncOpenAI(api_key=config.openai_api_key)
        # Most-recent turn's token usage, surfaced via report_usage().
        self._last_usage = Usage()

    @staticmethod
    def _build_messages(req: TurnRequest) -> list[dict]:
        """Prepend req.system as a system-role message ahead of the turn messages.

        Unlike Anthropic (separate `system=` channel), OpenAI Chat Completions
        carries the system prompt as the first message in the list.
        """
        messages: list[dict] = []
        system = (req.system or "").strip()
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(req.messages or [])
        return messages

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        # Model resolution: request override → Config default → hardcoded default.
        model = req.model or self.config.model or DEFAULT_MODEL
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=self._build_messages(req),
                max_completion_tokens=req.max_tokens,
                stream=True,
                # Ask for a trailing usage-only chunk so we can meter the turn.
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                # The final usage-only chunk has an empty `choices` list; earlier
                # chunks carry text on choices[0].delta.content.
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    text = getattr(delta, "content", None) if delta is not None else None
                    if text:
                        yield Delta(type="text", text=text)

                # `usage` is None on all chunks except the trailing one.
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    self._last_usage = Usage(
                        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    )
            yield Delta(type="done")
        except Exception as exc:  # noqa: BLE001 — surface any failure as an error Delta
            yield Delta(type="error", text=str(exc))

    def report_usage(self) -> Usage:
        return self._last_usage

    async def close(self) -> None:
        await self._client.close()
