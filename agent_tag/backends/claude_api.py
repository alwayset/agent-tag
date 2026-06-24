"""ClaudeApiBackend — Anthropic Claude via the official `anthropic` Python SDK.

This is the compliant, BYO-metered-key path (Config.anthropic_api_key): a shared
multi-user bot must NOT reuse subscription / coding-plan tokens (see config.py).

We use the async streaming helper `client.messages.stream(...)` (an async context
manager) and iterate `stream.text_stream` to surface text deltas as they arrive —
streaming avoids request timeouts on long inputs/outputs and lets the chat surface
show progress. After the stream drains, `await stream.get_final_message()` gives us
the accumulated `Message`, whose `.usage` (input_tokens / output_tokens) feeds
`report_usage()`.

The `anthropic` import is at module top level on purpose: the registry
(backends/registry.py) imports this module lazily and converts a missing SDK into a
friendly "pip install 'agent-tag[anthropic]'" error, so the core still runs without
the SDK installed.

SDK reference (verified 2026-06-24, anthropic >= 0.45):
https://platform.claude.com/docs/en/api/sdks/python  (§Async usage, §Streaming helpers)
  - from anthropic import AsyncAnthropic; AsyncAnthropic(api_key=...)
  - async with client.messages.stream(model=, max_tokens=, system=, messages=) as stream:
        async for text in stream.text_stream: ...
        message = await stream.get_final_message()  # message.usage.{input,output}_tokens
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic  # top-level: registry catches ImportError; core runs without the SDK

from agent_tag.backends.base import BackendAdapter, Delta, TurnRequest, Usage

# Default when neither the request nor Config pins a model.
DEFAULT_MODEL = "claude-opus-4-8"


class ClaudeApiBackend(BackendAdapter):
    name = "claude"

    def __init__(self, config) -> None:
        self.config = config
        # AsyncAnthropic also reads ANTHROPIC_API_KEY from the env, but we pass the
        # value off Config explicitly so the configured key is authoritative.
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        # Most-recent turn's token usage, surfaced via report_usage().
        self._last_usage = Usage()

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        # Model resolution: request override → Config default → hardcoded default.
        model = req.model or self.config.model or DEFAULT_MODEL
        try:
            async with self._client.messages.stream(
                model=model,
                max_tokens=req.max_tokens,
                system=req.system,
                messages=req.messages,
            ) as stream:
                async for chunk in stream.text_stream:
                    yield Delta(type="text", text=chunk)

                # Accumulated final message — pull normalized token usage off it.
                final = await stream.get_final_message()
                usage = getattr(final, "usage", None)
                if usage is not None:
                    self._last_usage = Usage(
                        input_tokens=getattr(usage, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage, "output_tokens", 0) or 0,
                    )
            yield Delta(type="done")
        except Exception as exc:  # noqa: BLE001 — surface any failure as an error Delta
            yield Delta(type="error", text=str(exc))

    def report_usage(self) -> Usage:
        return self._last_usage

    async def close(self) -> None:
        await self._client.close()
