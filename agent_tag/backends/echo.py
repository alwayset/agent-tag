"""EchoBackend — a no-LLM backend for tests/demo.

It needs no API key and proves the full pipeline end-to-end: it reflects the
turn's *metadata* (who is speaking, which channel, how many channel facts are
remembered) so you can watch per-channel memory accumulate and stay isolated
without spending a token.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from agent_tag.backends.base import BackendAdapter, Delta, TurnRequest


class EchoBackend(BackendAdapter):
    name = "echo"

    def __init__(self, config=None) -> None:
        pass

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        md = req.metadata
        user = md.get("user", "someone")
        channel = md.get("channel", "this channel")
        said = md.get("last_user_text", "")
        known = md.get("known_facts", [])
        reply = (
            f"(echo backend) Hi {user} — heard you in #{channel}: \"{said}\". "
            f"I currently remember {len(known)} note(s) about this channel."
        )
        if known:
            reply += " Most recent: " + known[0]
        yield Delta(type="text", text=reply)
        yield Delta(type="done")
