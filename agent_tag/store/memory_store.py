"""In-memory `Store` implementation — runs with zero infrastructure (tests / ephemeral).

The memory namespace fence is enforced here: `memory_search` filters strictly
by the namespace it is given. For a persistent deployment use `SqliteStore`.
"""
from __future__ import annotations

from agent_tag.models import (
    AuditEvent,
    Channel,
    ChannelPolicy,
    MemoryItem,
    Organization,
    TokenUsage,
    User,
    Workspace,
)
from agent_tag.store.base import Store


class InMemoryStore(Store):
    def __init__(self) -> None:
        self._orgs: dict[str, Organization] = {}
        self._workspaces: dict[str, Workspace] = {}
        self._users: dict[str, User] = {}
        self._channels: dict[str, Channel] = {}
        self._channels_by_ext: dict[tuple[str, str], str] = {}  # (platform, ext_id) -> channel_id
        self._policies: dict[str, ChannelPolicy] = {}
        self._memory: dict[str, list[MemoryItem]] = {}          # namespace -> items
        self._audit: list[AuditEvent] = []
        self._settings: dict[str, str] = {}
        self._usage: dict[str, TokenUsage] = {}

    # --- orgs / workspaces ---
    def put_org(self, org: Organization) -> None:
        self._orgs[org.id] = org

    def get_org(self, org_id: str) -> Organization | None:
        return self._orgs.get(org_id)

    def list_orgs(self) -> list[Organization]:
        return list(self._orgs.values())

    def put_workspace(self, ws: Workspace) -> None:
        self._workspaces[ws.id] = ws

    def get_workspace(self, ws_id: str) -> Workspace | None:
        return self._workspaces.get(ws_id)

    def list_workspaces(self, org_id: str | None = None) -> list[Workspace]:
        return [w for w in self._workspaces.values() if org_id is None or w.org_id == org_id]

    # --- users ---
    def put_user(self, user: User) -> None:
        self._users[user.id] = user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def find_user_by_identity(self, platform: str, external_user_id: str) -> User | None:
        for u in self._users.values():
            if u.identities.get(platform) == external_user_id:
                return u
        return None

    def list_users(self, org_id: str) -> list[User]:
        return [u for u in self._users.values() if u.org_id == org_id]

    # --- channels / policy ---
    def put_channel(self, ch: Channel) -> None:
        self._channels[ch.id] = ch
        self._channels_by_ext[(ch.platform, ch.external_id)] = ch.id

    def get_channel(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    def find_channel(self, platform: str, external_id: str) -> Channel | None:
        cid = self._channels_by_ext.get((platform, external_id))
        return self._channels.get(cid) if cid else None

    def list_channels(self, workspace_id: str | None = None) -> list[Channel]:
        return [c for c in self._channels.values()
                if workspace_id is None or c.workspace_id == workspace_id]

    def put_policy(self, policy: ChannelPolicy) -> None:
        self._policies[policy.channel_id] = policy

    def get_policy(self, channel_id: str) -> ChannelPolicy | None:
        return self._policies.get(channel_id)

    # --- memory (namespace-fenced) ---
    def memory_write(self, item: MemoryItem) -> None:
        self._memory.setdefault(item.namespace, []).append(item)

    def memory_search(self, namespace: str, query: str, limit: int = 10) -> list[MemoryItem]:
        items = self._memory.get(namespace, [])           # <-- the fence: this namespace only
        q = query.lower().strip()
        if not q:
            ranked = list(reversed(items))
        else:
            terms = set(q.split())
            ranked = sorted(
                items,
                key=lambda m: (sum(t in m.content.lower() for t in terms), m.created_at),
                reverse=True,
            )
        return ranked[:limit]

    def list_memory(self, namespace: str, limit: int = 200) -> list[MemoryItem]:
        return list(reversed(self._memory.get(namespace, [])))[:limit]

    def get_memory(self, item_id: str) -> MemoryItem | None:
        for items in self._memory.values():
            for m in items:
                if m.id == item_id:
                    return m
        return None

    def update_memory(self, item_id: str, content: str) -> bool:
        for items in self._memory.values():
            for m in items:
                if m.id == item_id:
                    m.content = content
                    return True
        return False

    def delete_memory(self, item_id: str) -> bool:
        for ns, items in self._memory.items():
            for i, m in enumerate(items):
                if m.id == item_id:
                    del items[i]
                    return True
        return False

    # --- audit ---
    def append_audit(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def list_audit(self, channel_id: str | None = None, limit: int = 200) -> list[AuditEvent]:
        rows = [e for e in self._audit if channel_id is None or e.channel_id == channel_id]
        return list(reversed(rows))[:limit]

    # --- settings ---
    def get_setting(self, key: str) -> str | None:
        return self._settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._settings[key] = value

    def all_settings(self) -> dict[str, str]:
        return dict(self._settings)

    # --- usage ---
    def add_usage(self, channel_id: str, input_tokens: int, output_tokens: int) -> None:
        u = self._usage.setdefault(channel_id, TokenUsage(channel_id=channel_id))
        u.input_tokens += input_tokens
        u.output_tokens += output_tokens

    def get_usage(self, channel_id: str) -> TokenUsage:
        return self._usage.get(channel_id) or TokenUsage(channel_id=channel_id)

    def list_usage(self) -> list[TokenUsage]:
        return list(self._usage.values())
