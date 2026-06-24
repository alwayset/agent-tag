"""Persistence interface.

Two implementations ship: `InMemoryStore` (tests / ephemeral) and `SqliteStore`
(the default for a real deployment — a single persistent file, zero infra). A
Postgres + pgvector store slots in here later for corpus ingestion (see TODO.md).

CAPABILITY FENCE (the trust property): `memory_search`/`memory_write` take the
namespace from trusted server-side turn context. The agent-facing memory *tool*
(core/memory.py) is bound to one namespace and exposes NO namespace parameter,
so a prompt-injected agent cannot read or write across channels.
"""
from __future__ import annotations

import abc

from agent_tag.models import (
    AuditEvent,
    Channel,
    ChannelPolicy,
    CorpusChunk,
    MemoryItem,
    Organization,
    TokenUsage,
    User,
    Workspace,
)


class Store(abc.ABC):
    # --- orgs / workspaces ---
    @abc.abstractmethod
    def put_org(self, org: Organization) -> None: ...
    @abc.abstractmethod
    def get_org(self, org_id: str) -> Organization | None: ...
    @abc.abstractmethod
    def list_orgs(self) -> list[Organization]: ...
    @abc.abstractmethod
    def put_workspace(self, ws: Workspace) -> None: ...
    @abc.abstractmethod
    def get_workspace(self, ws_id: str) -> Workspace | None: ...
    @abc.abstractmethod
    def list_workspaces(self, org_id: str | None = None) -> list[Workspace]: ...

    # --- users ---
    @abc.abstractmethod
    def put_user(self, user: User) -> None: ...
    @abc.abstractmethod
    def get_user(self, user_id: str) -> User | None: ...
    @abc.abstractmethod
    def find_user_by_identity(self, platform: str, external_user_id: str) -> User | None: ...
    @abc.abstractmethod
    def list_users(self, org_id: str) -> list[User]: ...

    # --- channels / policy ---
    @abc.abstractmethod
    def put_channel(self, ch: Channel) -> None: ...
    @abc.abstractmethod
    def get_channel(self, channel_id: str) -> Channel | None: ...
    @abc.abstractmethod
    def find_channel(self, platform: str, external_id: str) -> Channel | None: ...
    @abc.abstractmethod
    def list_channels(self, workspace_id: str | None = None) -> list[Channel]: ...
    @abc.abstractmethod
    def put_policy(self, policy: ChannelPolicy) -> None: ...
    @abc.abstractmethod
    def get_policy(self, channel_id: str) -> ChannelPolicy | None: ...

    # --- memory (namespace-fenced) ---
    @abc.abstractmethod
    def memory_write(self, item: MemoryItem) -> None: ...
    @abc.abstractmethod
    def memory_search(self, namespace: str, query: str, limit: int = 10) -> list[MemoryItem]:
        """Return memory items for `namespace` ONLY, regardless of `query`."""
    @abc.abstractmethod
    def list_memory(self, namespace: str, limit: int = 200) -> list[MemoryItem]: ...
    @abc.abstractmethod
    def get_memory(self, item_id: str) -> MemoryItem | None: ...
    @abc.abstractmethod
    def update_memory(self, item_id: str, content: str) -> bool: ...
    @abc.abstractmethod
    def delete_memory(self, item_id: str) -> bool: ...

    # --- audit ---
    @abc.abstractmethod
    def append_audit(self, event: AuditEvent) -> None: ...
    @abc.abstractmethod
    def list_audit(self, channel_id: str | None = None, limit: int = 200) -> list[AuditEvent]: ...

    # --- settings (UI-editable key/value config) ---
    @abc.abstractmethod
    def get_setting(self, key: str) -> str | None: ...
    @abc.abstractmethod
    def set_setting(self, key: str, value: str) -> None: ...
    @abc.abstractmethod
    def all_settings(self) -> dict[str, str]: ...

    # --- token usage / budget ---
    @abc.abstractmethod
    def add_usage(self, channel_id: str, input_tokens: int, output_tokens: int) -> None: ...
    @abc.abstractmethod
    def get_usage(self, channel_id: str) -> TokenUsage: ...
    @abc.abstractmethod
    def list_usage(self) -> list[TokenUsage]: ...

    # --- corpus (ingested org knowledge, workspace-scoped) ---
    @abc.abstractmethod
    def corpus_add(self, chunk: CorpusChunk) -> None: ...
    @abc.abstractmethod
    def corpus_search(self, workspace_id: str, query: str, limit: int = 6) -> list[CorpusChunk]:
        """Full-text retrieval over the workspace's ingested docs ONLY."""
    @abc.abstractmethod
    def corpus_clear(self, workspace_id: str, source: str | None = None) -> int: ...
    @abc.abstractmethod
    def corpus_docs(self, workspace_id: str) -> list[dict]:
        """Distinct docs: [{doc_id, title, url, source, chunks}], for the UI."""
    @abc.abstractmethod
    def corpus_count(self, workspace_id: str) -> int: ...
