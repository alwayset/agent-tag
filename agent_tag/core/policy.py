"""Lightweight policy checks used by the orchestrator."""

from __future__ import annotations

from agent_tag.adapters.base import InboundEvent
from agent_tag.models import ChannelPolicy


def should_respond(event: InboundEvent, policy: ChannelPolicy) -> bool:
    """MVP rule: respond when the bot is mentioned, unless the channel policy
    disables the mention requirement (ambient/LLM relevance gating is a v1
    feature — see TODO.md)."""
    if not policy.require_mention:
        return True
    return event.mentions_bot


def tool_allowed(policy: ChannelPolicy, tool_name: str) -> bool:
    return tool_name in policy.allowed_tools
