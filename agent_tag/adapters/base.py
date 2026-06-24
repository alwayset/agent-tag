"""IM platform adapter contract.

An Adapter normalizes a chat platform (Lark / Slack / Discord / console) into a
common `InboundEvent` stream and a `send` method. Implementing a new platform =
implementing this interface; nothing else in the system changes.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass(slots=True)
class FileRef:
    file_key: str
    name: str | None = None
    mime: str | None = None


@dataclass(slots=True)
class InboundEvent:
    platform: str  # "lark" | "slack" | "discord" | "console"
    channel_id: str  # platform-native channel/chat id
    user_id: str  # platform-native sender id
    text: str
    mentions_bot: bool = False
    thread_id: str | None = None
    message_id: str | None = None
    user_display_name: str | None = None
    files: list[FileRef] = field(default_factory=list)
    raw: dict | None = None


@dataclass(slots=True)
class HistoryMsg:
    user_id: str
    text: str
    is_bot: bool = False
    user_display_name: str | None = None


class Adapter(abc.ABC):
    """Subclasses set `platform` and implement `stream_inbound` + `send`."""

    platform: str = "base"

    @abc.abstractmethod
    def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        """Async generator yielding normalized inbound events.

        Implementations are `async def` generators that `yield InboundEvent(...)`.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def send(self, channel_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a message; return a platform message id if available."""

    async def edit(self, channel_id: str, message_id: str, text: str) -> None:
        """Optional: edit a previously-sent message (for streaming cards)."""
        return None

    async def fetch_history(
        self, channel_id: str, *, thread_id: str | None = None, limit: int = 20
    ) -> list[HistoryMsg]:
        return []

    async def fetch_file(self, file_ref: FileRef) -> bytes | None:
        return None

    async def close(self) -> None:
        return None
