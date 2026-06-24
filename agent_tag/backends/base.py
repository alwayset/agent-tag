"""Agent backend contract — the harness seam.

Agent Tag does NOT implement its own agent loop. It rents one behind this
interface: Claude (Anthropic API), Codex/OpenAI, a local coding-agent CLI, or
any agent that speaks the Agent Client Protocol (ACP). Staying agent-agnostic
while reusing one harness is exactly this seam.

A backend receives a `TurnRequest` (system + messages + optional tools/metadata)
and streams `Delta`s back. Token accounting is normalized via `report_usage`.
"""
from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class Delta:
    type: str                 # "text" | "tool_call" | "done" | "error"
    text: str = ""
    data: dict | None = None


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(slots=True)
class TurnRequest:
    system: str
    messages: list[dict]                      # [{"role": "user"|"assistant", "content": str}]
    tools: list[dict] = field(default_factory=list)
    model: str | None = None
    max_tokens: int = 1024
    metadata: dict = field(default_factory=dict)  # non-LLM context (channel, user, known_facts)


class BackendAdapter(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        """Async generator streaming the agent's response for one turn."""
        raise NotImplementedError

    def report_usage(self) -> Usage:
        return Usage()

    async def close(self) -> None:
        return None
