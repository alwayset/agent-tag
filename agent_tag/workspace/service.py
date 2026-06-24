"""WorkspaceService — organization, multi-user, and channel-binding logic.

This is where "support different users within an organization" lives: a person
who @-mentions the teammate on any platform is resolved (or auto-enrolled) to a
single org `User`, so the teammate knows *who* it is talking to and what role
they have. Channels are bound to a workspace and carry a `ChannelPolicy`.
"""
from __future__ import annotations

import uuid

from agent_tag.models import (
    Channel,
    ChannelPolicy,
    Organization,
    Role,
    User,
    Workspace,
)
from agent_tag.store.base import Store


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class WorkspaceService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # --- org / workspace ---
    def create_org(self, name: str, *, org_id: str | None = None) -> Organization:
        org = Organization(id=org_id or _id("org"), name=name)
        self.store.put_org(org)
        return org

    def create_workspace(self, org_id: str, name: str, *, ws_id: str | None = None) -> Workspace:
        ws = Workspace(id=ws_id or _id("ws"), org_id=org_id, name=name)
        self.store.put_workspace(ws)
        return ws

    # --- users ---
    def add_user(
        self,
        org_id: str,
        display_name: str,
        *,
        role: Role = Role.MEMBER,
        identities: dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> User:
        user = User(
            id=user_id or _id("usr"),
            org_id=org_id,
            display_name=display_name,
            role=role,
            identities=dict(identities or {}),
        )
        self.store.put_user(user)
        return user

    def resolve_user(
        self, org_id: str, platform: str, external_user_id: str, display_name: str | None = None
    ) -> User:
        """Find the org User for this platform identity, auto-enrolling as a
        MEMBER on first contact. This is what lets many people share one teammate."""
        user = self.store.find_user_by_identity(platform, external_user_id)
        if user is not None:
            if display_name and user.display_name in (None, "", external_user_id):
                user.display_name = display_name
                self.store.put_user(user)
            return user
        user = self.add_user(
            org_id,
            display_name or external_user_id,
            role=Role.MEMBER,
            identities={platform: external_user_id},
        )
        return user

    def link_identity(self, user_id: str, platform: str, external_user_id: str) -> None:
        user = self.store.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        user.identities[platform] = external_user_id
        self.store.put_user(user)

    # --- channels / policy ---
    def bind_channel(
        self,
        workspace_id: str,
        platform: str,
        external_id: str,
        name: str,
        *,
        backend: str = "echo",
        model: str | None = None,
        require_mention: bool = True,
        admin_user_ids: list[str] | None = None,
    ) -> tuple[Channel, ChannelPolicy]:
        existing = self.store.find_channel(platform, external_id)
        if existing is not None:
            policy = self.store.get_policy(existing.id)
            assert policy is not None
            return existing, policy
        ch = Channel(
            id=_id("chan"),
            workspace_id=workspace_id,
            platform=platform,
            external_id=external_id,
            name=name,
        )
        self.store.put_channel(ch)
        policy = ChannelPolicy(
            channel_id=ch.id,
            memory_namespace=f"{platform}:{external_id}",
            backend=backend,
            model=model,
            require_mention=require_mention,
            admin_user_ids=list(admin_user_ids or []),
        )
        self.store.put_policy(policy)
        return ch, policy

    def get_channel(self, platform: str, external_id: str) -> Channel | None:
        return self.store.find_channel(platform, external_id)

    def get_policy(self, channel_id: str) -> ChannelPolicy | None:
        return self.store.get_policy(channel_id)

    def is_admin(self, user: User, policy: ChannelPolicy) -> bool:
        return user.role in (Role.OWNER, Role.ADMIN) or user.id in policy.admin_user_ids
