"""MemoryService — the distilled, per-channel knowledge entity (智库, MVP slice).

Two ideas matter here:

1. CAPABILITY FENCE. `bind(namespace)` returns a `ScopedMemory` whose `search`
   and `write` are locked to one namespace. The agent-facing tool schema has no
   namespace parameter, so a prompt-injected agent literally cannot phrase a
   cross-channel query. The namespace always comes from trusted turn context.

2. DISTILL, DON'T DUMP. We store short distilled notes ("X decided Y"), not raw
   transcripts — raw history as context invites token bloat, memory poisoning,
   and stale facts. (Real LLM-based distillation is a TODO; MVP stores a compact
   interaction note.) Retrieved memory is treated as DATA, never instructions.
"""

from __future__ import annotations

import time
import uuid

from agent_tag.models import MemoryItem
from agent_tag.store.base import Store


class ScopedMemory:
    """A namespace-locked handle. This is what (indirectly) backs the agent's
    memory tool — note there is no way to pass a different namespace."""

    def __init__(self, store: Store, namespace: str) -> None:
        self._store = store
        self._namespace = namespace

    @property
    def namespace(self) -> str:
        return self._namespace

    def search(self, query: str = "", limit: int = 10) -> list[MemoryItem]:
        return self._store.memory_search(self._namespace, query, limit)

    def write(
        self,
        content: str,
        *,
        kind: str = "fact",
        provenance: str = "agent",
        ttl_seconds: float | None = None,
    ) -> MemoryItem:
        now = time.time()
        item = MemoryItem(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            namespace=self._namespace,
            kind=kind,
            content=content.strip()[:2000],
            provenance=provenance,
            created_at=now,
            decay_at=(now + ttl_seconds) if ttl_seconds else None,
        )
        self._store.memory_write(item)
        return item


class MemoryService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def bind(self, namespace: str) -> ScopedMemory:
        return ScopedMemory(self.store, namespace)
