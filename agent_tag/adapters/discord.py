"""DiscordAdapter — normalizes Discord (via discord.py v2.x) into the common
`InboundEvent` stream + `send` contract.

Install the extra: `pip install 'agent-tag[discord]'` (pulls `discord.py>=2.4`).

Design notes
------------
* discord.py is event-driven: a `discord.Client` connects to the gateway and
  fires `on_message` callbacks on its own event loop. There is no native
  "async generator of messages", so we bridge the callback world to the
  generator world with an `asyncio.Queue`. `on_message` pushes a normalized
  `InboundEvent`; `stream_inbound` pops from the queue and yields.
* `client.start(token)` is the awaitable login+connect coroutine (the
  non-blocking sibling of the blocking `client.run`). We launch it as a
  background task so `stream_inbound` can keep yielding while the client runs.
* `message_content` is a PRIVILEGED gateway intent — it must be enabled both
  here (`intents.message_content = True`) AND in the Discord Developer Portal
  for the bot, or `message.content` arrives empty.

API verified against discord.py stable docs (2026):
https://discordpy.readthedocs.io/en/stable/api.html
  - discord.Intents.default() + .message_content
  - discord.Client(intents=...), @client.event on_message
  - await client.start(token, *, reconnect=True) / await client.close()
  - Message.channel / .author / .mentions / .id / .content
  - discord.Thread (isinstance check for thread detection)
  - Client.get_channel(id) (cache) / await fetch_channel(id) (API)
  - TextChannel.send(...) / Thread.send(...)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import discord  # optional dep; registry catches ImportError and tells user to install extra

from agent_tag.adapters.base import Adapter, HistoryMsg, InboundEvent


class DiscordAdapter(Adapter):
    platform = "discord"

    def __init__(self, config) -> None:
        self.config = config
        self._token: str | None = getattr(config, "discord_token", None)

        # message_content is a privileged intent (also enable it in the Dev Portal).
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        # Bridge: on_message (runs on the client's loop) -> queue -> stream_inbound.
        self._queue: asyncio.Queue[InboundEvent] = asyncio.Queue()
        self._client_task: asyncio.Task | None = None

        # Register the gateway message handler.
        @self._client.event
        async def on_message(message: discord.Message) -> None:  # noqa: ANN001 (discord signature)
            # Skip our own messages (and anything from this exact bot user) to
            # avoid feedback loops.
            if self._client.user is not None and message.author.id == self._client.user.id:
                return

            text = self._strip_bot_mention(message)
            mentions_bot = (
                self._client.user is not None and self._client.user in message.mentions
            )

            # A message lives "in a thread" when its channel is a discord.Thread.
            thread_id = (
                str(message.channel.id)
                if isinstance(message.channel, discord.Thread)
                else None
            )

            await self._queue.put(
                InboundEvent(
                    platform=self.platform,
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    user_display_name=getattr(
                        message.author, "display_name", None
                    )
                    or str(message.author),
                    text=text,
                    mentions_bot=mentions_bot,
                    thread_id=thread_id,
                    message_id=str(message.id),
                    raw={"message": message},
                )
            )

    # ------------------------------------------------------------------ helpers

    def _strip_bot_mention(self, message: discord.Message) -> str:
        """Return message text with this bot's @-mention removed.

        Discord encodes a user mention in raw content as `<@id>` or `<@!id>`.
        We strip both forms for our own user so the backend sees clean text.
        """
        text = message.content or ""
        me = self._client.user
        if me is not None:
            for token in (f"<@{me.id}>", f"<@!{me.id}>"):
                text = text.replace(token, "")
        return text.strip()

    async def _resolve_channel(self, channel_id: str):
        """Get a channel/thread object by id — cache first, then API."""
        cid = int(channel_id)
        channel = self._client.get_channel(cid)
        if channel is None:
            channel = await self._client.fetch_channel(cid)
        return channel

    # -------------------------------------------------------------- inbound

    async def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        if not self._token:
            raise RuntimeError("discord_token is not configured")

        # Launch the gateway client as a background task (start = login + connect;
        # the awaitable, non-blocking counterpart of client.run).
        if self._client_task is None:
            self._client_task = asyncio.create_task(self._client.start(self._token))

        while True:
            # Surface a crashed client task instead of hanging on the queue forever.
            if self._client_task.done():
                exc = self._client_task.exception()
                if exc is not None:
                    raise exc
                return  # client closed cleanly

            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # re-check client_task liveness, then keep waiting
            yield event

    # -------------------------------------------------------------- outbound

    async def send(
        self, channel_id: str, text: str, *, thread_id: str | None = None
    ) -> str | None:
        # Thread-aware: if a thread_id is given, post into the thread; otherwise
        # post into the channel. Both discord.Thread and discord.TextChannel
        # expose the same `.send(content)` coroutine returning a Message.
        target_id = thread_id or channel_id
        channel = await self._resolve_channel(target_id)
        sent = await channel.send(text)
        return str(sent.id)

    async def edit(self, channel_id: str, message_id: str, text: str) -> None:
        channel = await self._resolve_channel(channel_id)
        message = await channel.fetch_message(int(message_id))
        await message.edit(content=text)

    async def fetch_history(
        self, channel_id: str, *, thread_id: str | None = None, limit: int = 20
    ) -> list[HistoryMsg]:
        target_id = thread_id or channel_id
        channel = await self._resolve_channel(target_id)
        out: list[HistoryMsg] = []
        # channel.history() is an async iterator (newest-first); reverse to
        # chronological order for the backend.
        async for message in channel.history(limit=limit):
            out.append(
                HistoryMsg(
                    user_id=str(message.author.id),
                    text=message.content or "",
                    is_bot=bool(message.author.bot),
                    user_display_name=getattr(message.author, "display_name", None)
                    or str(message.author),
                )
            )
        out.reverse()
        return out

    async def close(self) -> None:
        if not self._client.is_closed():
            await self._client.close()
        if self._client_task is not None:
            try:
                await self._client_task
            except (asyncio.CancelledError, Exception):
                # Client task ending during shutdown is expected; swallow.
                pass
            self._client_task = None
