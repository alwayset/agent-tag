"""Router — maps a raw inbound chat event to (user, channel, workspace, policy).

New people are auto-enrolled as org members; for MVP, unknown channels are
auto-bound to a default workspace. (Admin-gated channel onboarding instead of
auto-bind is a v1 item — see TODO.md.)
"""
from __future__ import annotations

from dataclasses import dataclass

from agent_tag.adapters.base import InboundEvent
from agent_tag.models import Channel, ChannelPolicy, User, Workspace
from agent_tag.workspace.service import WorkspaceService


@dataclass(slots=True)
class Resolution:
    user: User
    channel: Channel
    workspace: Workspace
    policy: ChannelPolicy


class Router:
    def __init__(
        self,
        workspace: WorkspaceService,
        *,
        default_org_id: str,
        default_workspace_id: str,
        default_backend: str = "echo",
        default_model: str | None = None,
        auto_bind: bool = True,
        require_mention: bool = True,
    ) -> None:
        self.ws = workspace
        self.default_org_id = default_org_id
        self.default_workspace_id = default_workspace_id
        self.default_backend = default_backend
        self.default_model = default_model
        self.auto_bind = auto_bind
        self.require_mention = require_mention

    def resolve(self, event: InboundEvent) -> Resolution | None:
        channel = self.ws.get_channel(event.platform, event.channel_id)
        if channel is None:
            if not self.auto_bind:
                return None
            channel, _ = self.ws.bind_channel(
                self.default_workspace_id,
                event.platform,
                event.channel_id,
                name=event.channel_id,
                backend=self.default_backend,
                model=self.default_model,
                require_mention=self.require_mention,
            )
        policy = self.ws.get_policy(channel.id)
        assert policy is not None
        workspace = self.ws.store.get_workspace(channel.workspace_id)
        assert workspace is not None
        user = self.ws.resolve_user(
            workspace.org_id, event.platform, event.user_id, event.user_display_name
        )
        return Resolution(user=user, channel=channel, workspace=workspace, policy=policy)
