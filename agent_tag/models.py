"""Core domain model for Agent Tag.

The unit of value is a *channel* (a shared teammate lives in a chat channel).
Channels belong to a *workspace*, workspaces belong to an *organization*, and
*users* are members of an organization who reach the teammate from one or more
chat *platforms* (Lark / Slack / Discord).

This module is pure data + zero third-party deps so the whole core runs on a
bare Python install.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


@dataclass(slots=True)
class Organization:
    id: str
    name: str


@dataclass(slots=True)
class User:
    """A person in the org. `identities` maps a platform name to that platform's
    native user id, so the same human is one User across Lark/Slack/Discord."""
    id: str
    org_id: str
    display_name: str
    role: Role = Role.MEMBER
    identities: dict[str, str] = field(default_factory=dict)  # platform -> external_user_id


@dataclass(slots=True)
class Workspace:
    id: str
    org_id: str
    name: str


@dataclass(slots=True)
class Channel:
    """A bound chat channel the teammate participates in."""
    id: str
    workspace_id: str
    platform: str          # "lark" | "slack" | "discord" | "console"
    external_id: str       # platform-native channel/chat id
    name: str


@dataclass(slots=True)
class ChannelPolicy:
    """Per-channel governance + behavior. This is the 'spine' object — one per
    bound channel. Memory and tool access are scoped through it."""
    channel_id: str
    memory_namespace: str                       # hard-isolation key, e.g. "lark:oc_123"
    backend: str = "echo"                        # which agent backend powers this channel
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    redaction_enabled: bool = True
    ambient_enabled: bool = False
    ambient_interval_hours: int = 24             # deterministic nudge cadence
    require_mention: bool = True
    admin_user_ids: list[str] = field(default_factory=list)
    token_budget: int | None = None             # max total tokens/period; None = unlimited
    display_name: str = ""                        # friendly label shown in the admin UI


@dataclass(slots=True)
class TokenUsage:
    channel_id: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class MemoryItem:
    """A distilled fact/decision — NOT a raw transcript. Scoped by `namespace`."""
    id: str
    namespace: str
    kind: str          # "interaction" | "fact" | "decision"
    content: str
    provenance: str    # who/what produced it
    created_at: float
    decay_at: float | None = None


@dataclass(slots=True)
class CorpusChunk:
    """A chunk of an ingested org document (Lark wiki/doc/drive, etc.), indexed
    for query-time retrieval. Workspace-scoped — the org knowledge base (智库)."""
    workspace_id: str
    source: str            # e.g. "lark-wiki:<space_id>"
    doc_id: str
    title: str
    url: str
    chunk_idx: int
    text: str
    score: float = 0.0


@dataclass(slots=True)
class AuditEvent:
    id: str
    ts: float
    channel_id: str
    actor: str             # user id, or "ambient" for autonomous actions
    requested_by: str | None
    action: str            # "respond" | "tool_call" | "memory_write" | "denied" ...
    detail: str = ""
    outcome: str = "ok"
