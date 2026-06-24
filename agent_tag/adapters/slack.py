"""SlackAdapter — Slack platform adapter built on Bolt for Python in Socket Mode.

Socket Mode keeps a single outbound WebSocket open to Slack, so the bot receives
events without exposing a public HTTP endpoint (no ngrok / Request URL needed).
This makes it work the same on a laptop as on a server.

Two tokens are required (read off `config`):
  * slack_bot_token  — bot user OAuth token, "xoxb-..." (Web API calls)
  * slack_app_token  — app-level token, "xapp-..." with `connections:write`
                       (opens the Socket Mode WebSocket)

Required Slack app scopes / settings:
  * Socket Mode: ON; an app-level token with `connections:write`.
  * Event Subscriptions: subscribe to `app_mention` (and `message.channels` /
    `message.im` if you want non-mention messages too).
  * Bot scopes: `app_mentions:read`, `chat:write`, `channels:history`,
    `groups:history`, `im:history`, `mpim:history` (history scopes power
    fetch_history), and `files:read` if you fetch files.

Verified against the current (2026) Bolt for Python async API:
  * slack_bolt.app.async_app.AsyncApp(token=...)
  * @app.event("app_mention") / @app.event("message") async handlers
  * slack_bolt.adapter.socket_mode.async_handler.AsyncSocketModeHandler(app, app_token)
    started via `await handler.start_async()`
  * AsyncWebClient (app.client): chat_postMessage / chat_update /
    conversations_history / conversations_replies
  Docs:
    - https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
    - https://github.com/slackapi/bolt-python/blob/main/examples/socket_mode_async.py
    - https://docs.slack.dev/tools/python-slack-sdk/reference/web/async_client.html
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

# Imported at module top-level on purpose: the adapter registry only imports this
# module when the "slack" adapter is selected, and catches ImportError to tell the
# user to `pip install 'agent-tag[slack]'`. The core runs fine without slack_bolt.
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp

from agent_tag.adapters.base import Adapter, FileRef, HistoryMsg, InboundEvent

# Matches a leading bot mention like "<@U12345>" (optionally "<@U12345|name>")
# so we can strip it from app_mention text and hand the backend the clean prompt.
_LEADING_MENTION = re.compile(r"^\s*<@([A-Z0-9]+)(?:\|[^>]+)?>\s*")


class SlackAdapter(Adapter):
    platform = "slack"

    def __init__(self, config) -> None:
        self.config = config
        self._app = AsyncApp(token=config.slack_bot_token)
        self._app_token = config.slack_app_token
        # AsyncWebClient pre-authed with the bot token; use for all Web API calls.
        self._client = self._app.client
        # Inbound events flow handler-thread -> queue -> stream_inbound generator.
        self._queue: asyncio.Queue[InboundEvent] = asyncio.Queue()
        # The Socket Mode handler + its background task (started in stream_inbound).
        self._handler: AsyncSocketModeHandler | None = None
        self._handler_task: asyncio.Task | None = None
        # Cache the bot's own user id so we can flag self-authored history messages.
        self._bot_user_id: str | None = None
        self._register_handlers()

    # ------------------------------------------------------------------ handlers
    def _register_handlers(self) -> None:
        """Register Bolt event listeners that enqueue normalized InboundEvents."""

        @self._app.event("app_mention")
        async def _on_app_mention(event: dict) -> None:
            # Direct @-mention of the bot: always counts as addressing the bot.
            self._enqueue(event, mentions_bot=True)

        @self._app.event("message")
        async def _on_message(event: dict) -> None:
            # Catch-all for plain channel/DM messages (only delivered if the app is
            # subscribed to message.* events). Skip:
            #   * subtypes (edits, joins, bot_message, etc.) — only handle the
            #     normal user-authored "text" case,
            #   * the bot's own messages (avoid feedback loops),
            #   * messages that are app_mentions (already handled above — Slack
            #     delivers a mention as BOTH app_mention and message).
            if event.get("subtype"):
                return
            if event.get("bot_id"):
                return
            text = event.get("text") or ""
            mentions_bot = bool(self._bot_user_id and f"<@{self._bot_user_id}>" in text)
            if mentions_bot:
                # Already surfaced via the app_mention handler; don't double-emit.
                return
            self._enqueue(event, mentions_bot=False)

    def _enqueue(self, event: dict, *, mentions_bot: bool) -> None:
        """Normalize a raw Slack event dict and push it onto the queue."""
        raw_text = event.get("text") or ""
        # Strip a single leading bot mention so the backend sees a clean prompt.
        text = _LEADING_MENTION.sub("", raw_text, count=1) if mentions_bot else raw_text
        ts = event.get("ts")
        ev = InboundEvent(
            platform=self.platform,
            channel_id=event.get("channel", ""),
            user_id=event.get("user", ""),
            text=text,
            mentions_bot=mentions_bot,
            # Reply into the existing thread if any, else start one rooted at this msg.
            thread_id=event.get("thread_ts") or ts,
            message_id=ts,
            files=self._extract_files(event),
            raw=event,
        )
        self._queue.put_nowait(ev)

    @staticmethod
    def _extract_files(event: dict) -> list[FileRef]:
        files: list[FileRef] = []
        for f in event.get("files", []) or []:
            files.append(
                FileRef(
                    # url_private is the authenticated download URL; fall back to id.
                    file_key=f.get("url_private") or f.get("id", ""),
                    name=f.get("name"),
                    mime=f.get("mimetype"),
                )
            )
        return files

    # -------------------------------------------------------------- stream_inbound
    async def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        """Start the Socket Mode connection in the background and drain the queue."""
        # Resolve + cache the bot's own user id (best-effort; used to dedupe/self-skip).
        try:
            auth = await self._client.auth_test()
            self._bot_user_id = auth.get("user_id")
        except Exception:
            self._bot_user_id = None

        # AsyncSocketModeHandler runs the WebSocket; start_async() blocks forever,
        # so we run it as a background task and yield events as they arrive.
        self._handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._handler_task = asyncio.create_task(self._handler.start_async())

        try:
            while True:
                yield await self._queue.get()
        finally:
            await self.close()

    # --------------------------------------------------------------------- send
    async def send(
        self, channel_id: str, text: str, *, thread_id: str | None = None
    ) -> str | None:
        # thread_ts must be a string ts; passing the parent's ts threads the reply.
        resp = await self._client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_id,
        )
        # Posted message ts is the platform message id (usable as message_id for edit).
        return resp.get("ts")

    # --------------------------------------------------------------------- edit
    async def edit(self, channel_id: str, message_id: str, text: str) -> None:
        await self._client.chat_update(channel=channel_id, ts=message_id, text=text)

    # ------------------------------------------------------------- fetch_history
    async def fetch_history(
        self, channel_id: str, *, thread_id: str | None = None, limit: int = 20
    ) -> list[HistoryMsg]:
        if thread_id:
            # conversations.replies returns the thread root + replies, oldest first.
            resp = await self._client.conversations_replies(
                channel=channel_id, ts=thread_id, limit=limit
            )
        else:
            # conversations.history returns the channel timeline, newest first.
            resp = await self._client.conversations_history(
                channel=channel_id, limit=limit
            )
        messages = resp.get("messages", []) or []
        if not thread_id:
            # Normalize to chronological order to match the threaded case.
            messages = list(reversed(messages))

        out: list[HistoryMsg] = []
        for m in messages:
            # Skip non-message events (channel joins, etc.) that carry no user text.
            if m.get("subtype") and not m.get("bot_id"):
                continue
            out.append(
                HistoryMsg(
                    user_id=m.get("user") or m.get("bot_id") or "",
                    text=m.get("text") or "",
                    # A message is the bot's if it has bot_id or is authored by us.
                    is_bot=bool(m.get("bot_id"))
                    or (self._bot_user_id is not None and m.get("user") == self._bot_user_id),
                )
            )
        return out

    # --------------------------------------------------------------- fetch_file
    async def fetch_file(self, file_ref: FileRef) -> bytes | None:
        """Download a Slack file. url_private requires the bot token as a Bearer auth.

        The Slack Web API client doesn't expose a generic file-bytes fetch, so we
        use its underlying aiohttp session-style call via the bot token header.
        """
        url = file_ref.file_key
        if not url or not url.startswith("http"):
            return None
        token = self.config.slack_bot_token
        try:
            import aiohttp  # provided by the [slack] extra alongside slack-bolt
        except ImportError:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()

    # -------------------------------------------------------------------- close
    async def close(self) -> None:
        # Stop the Socket Mode WebSocket and cancel its background task.
        if self._handler is not None:
            try:
                await self._handler.close_async()
            except Exception:
                pass
        if self._handler_task is not None:
            self._handler_task.cancel()
            try:
                await self._handler_task
            except (asyncio.CancelledError, Exception):
                pass
            self._handler_task = None
