"""LarkAdapter — Lark / Feishu IM platform adapter.

Uses the official `lark-oapi` Python SDK (https://github.com/larksuite/oapi-sdk-python,
verified against lark-oapi 1.6.9 on 2026-06-24).

Inbound events arrive over a **WebSocket long-connection** client
(`lark_oapi.ws.Client`) subscribed to `im.message.receive_v1`. That client uses a
synchronous callback/handler model and a *blocking* `start()` call, so we:

  1. register a sync callback on an `EventDispatcherHandler`,
  2. run `ws.Client.start()` in a background thread (executor),
  3. bridge each callback into the async world by pushing the normalized
     `InboundEvent` onto an `asyncio.Queue` via `loop.call_soon_threadsafe`,
  4. have `stream_inbound()` (an async generator) drain that queue.

Outbound calls use the SDK's async API surface (`acreate` / `areply` / `aget`),
so no extra threading is needed for sends/replies/file fetches.

Relevant SDK docs:
  - WS long-connection client + register_p2_im_message_receive_v1:
    https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
  - Send message (im.v1.message.create, receive_id_type/msg_type/content):
    https://open.larksuite.com/document/server-docs/im-v1/message/create
  - Reply message (im.v1.message.reply, reply_in_thread):
    https://open.larksuite.com/document/server-docs/im-v1/message/reply
  - Get message resource (im.v1.message_resource.get, file_key + type):
    https://open.larksuite.com/document/server-docs/im-v1/message/get-2
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from agent_tag.adapters.base import Adapter, FileRef, InboundEvent

logger = logging.getLogger(__name__)

# Sentinel pushed onto the queue when the WS background thread stops, so the
# async generator can terminate cleanly instead of blocking forever.
_STOP = object()

# Mention placeholder tokens that Lark embeds in message text, e.g. the text of
# a message that @-mentions a user is "@_user_1 hello". The real display name
# lives in message.mentions[i].name keyed by message.mentions[i].key.
_MENTION_TOKEN_RE = re.compile(r"@_(?:user|all)_\w+")


class LarkAdapter(Adapter):
    """Lark/Feishu adapter. Set LARK_DOMAIN to open.feishu.cn for Feishu."""

    platform = "lark"

    def __init__(self, config) -> None:
        self.config = config
        if not config.lark_app_id or not config.lark_app_secret:
            raise ValueError(
                "LarkAdapter requires lark_app_id + lark_app_secret "
                "(set LARK_APP_ID / LARK_APP_SECRET)."
            )
        self._domain: str = config.lark_domain or lark.LARK_DOMAIN

        # HTTP client for outbound calls (send / reply / fetch_file). Separate
        # from the WS client, which is inbound-only.
        self._client: lark.Client = (
            lark.Client.builder()
            .app_id(config.lark_app_id)
            .app_secret(config.lark_app_secret)
            .domain(self._domain)
            .build()
        )

        # WS long-connection client; built lazily in stream_inbound() so we can
        # bind it to the running event loop + queue.
        self._ws_client: lark.ws.Client | None = None
        self._queue: asyncio.Queue[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_task: asyncio.Future | None = None
        self._closed = False

    # --------------------------------------------------------------------- #
    # Inbound: WS long-connection -> asyncio.Queue -> async generator
    # --------------------------------------------------------------------- #
    def _on_message(self, data: P2ImMessageReceiveV1) -> None:
        """Sync callback invoked by the WS client thread for each message.

        We must not block here and we are NOT on the event loop thread, so we
        normalize then hand the event to the loop thread-safely.
        """
        try:
            event = self._normalize(data)
        except Exception:  # never let a bad payload kill the WS thread
            logger.exception("LarkAdapter: failed to normalize inbound message")
            return
        if event is None or self._loop is None or self._queue is None:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    def _normalize(self, data: P2ImMessageReceiveV1) -> InboundEvent | None:
        ev = data.event
        if ev is None or ev.message is None:
            return None
        msg = ev.message
        sender = ev.sender

        # Sender open_id (preferred stable id for a user across the tenant).
        user_id = ""
        if sender is not None and sender.sender_id is not None:
            user_id = sender.sender_id.open_id or sender.sender_id.user_id or ""

        # Text: message.content is a JSON string; for msg_type == "text" it is
        # {"text": "..."}. Other types (image/file/post) have no plain text.
        text = ""
        if msg.message_type == "text" and msg.content:
            try:
                text = (json.loads(msg.content) or {}).get("text", "") or ""
            except (ValueError, TypeError):
                text = ""

        # Strip @mention placeholder tokens ("@_user_1") from the text.
        if text:
            text = _MENTION_TOKEN_RE.sub("", text)
            text = re.sub(r"\s{2,}", " ", text).strip()

        # mentions_bot: a 1:1 ("p2p") chat is implicitly directed at the bot;
        # in group chats Lark only delivers receive_v1 to a bot that was
        # actually @-mentioned, so any mention present means us.
        mentions = msg.mentions or []
        mentions_bot = (msg.chat_type == "p2p") or bool(mentions)

        # thread_id: prefer the explicit thread_id, then root_id (a reply's
        # thread anchor) so replies land in the same thread.
        thread_id = msg.thread_id or msg.root_id or None

        # Files: image / file / audio / media messages carry a resource the bot
        # can pull via message_resource. The file_key lives in the content JSON.
        files: list[FileRef] = []
        if msg.message_type in ("image", "file", "audio", "media") and msg.content:
            files = self._extract_files(msg.message_type, msg.content, msg.message_id or "")

        return InboundEvent(
            platform=self.platform,
            channel_id=msg.chat_id or "",
            user_id=user_id,
            text=text,
            mentions_bot=mentions_bot,
            thread_id=thread_id,
            message_id=msg.message_id,
            files=files,
            raw={"chat_type": msg.chat_type, "message_type": msg.message_type},
        )

    @staticmethod
    def _extract_files(message_type: str, content: str, message_id: str) -> list[FileRef]:
        """Pull FileRef(s) out of an image/file/audio/media message content JSON.

        The Lark resource-download endpoint (message_resource.get) needs BOTH the
        message_id and the resource key. `FileRef` (a locked interface) has no
        message_id field, so we encode it into `file_key` as
        ``"<message_id>|<resource_key>"`` and split it back out in fetch_file().
        The resource `type` ("image" vs "file") is carried in `FileRef.mime`.

        Lark resource messages carry an `image_key` (image) or `file_key`
        (file/audio/media) in the content JSON.
        """
        try:
            body = json.loads(content) or {}
        except (ValueError, TypeError):
            return []
        if message_type == "image":
            key = body.get("image_key")
            if not key:
                return []
            return [FileRef(file_key=f"{message_id}|{key}", name=None, mime="image")]
        key = body.get("file_key")
        if not key:
            return []
        name = body.get("file_name")
        return [FileRef(file_key=f"{message_id}|{key}", name=name, mime="file")]

    async def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        # ws.Client.start() is synchronous + blocking and runs its OWN asyncio
        # loop via run_until_complete. So it must own a fresh event loop on the
        # worker thread — and the Client must be CONSTRUCTED on that same thread,
        # otherwise lark-oapi binds to the main running loop and start() fails
        # with "This event loop is already running". Exceptions are surfaced via
        # the sentinel so the generator can stop.
        def _run_ws() -> None:
            # lark-oapi's ws client drives a MODULE-LEVEL `loop` it captured at
            # import time (the app's main loop). We repoint it at a fresh,
            # non-running loop on this worker thread so its run_until_complete
            # calls don't collide with the running main loop.
            import lark_oapi.ws.client as _ws_mod

            worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(worker_loop)
            _ws_mod.loop = worker_loop
            try:
                self._ws_client = lark.ws.Client(
                    self.config.lark_app_id,
                    self.config.lark_app_secret,
                    event_handler=handler,
                    domain=self._domain,
                    log_level=lark.LogLevel.INFO,
                )
                self._ws_client.start()  # blocks until the connection is torn down
            except Exception:
                logger.exception("LarkAdapter: WS client stopped with error")
            finally:
                if self._loop is not None and self._queue is not None:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, _STOP)

        self._ws_task = self._loop.run_in_executor(None, _run_ws)

        try:
            while True:
                item = await self._queue.get()
                if item is _STOP or self._closed:
                    break
                yield item
        finally:
            await self.close()

    # --------------------------------------------------------------------- #
    # Outbound
    # --------------------------------------------------------------------- #
    async def send(self, channel_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a text message to a chat.

        If `thread_id` looks like a message_id (om_...) we reply to it so the
        message threads correctly; otherwise we post a fresh message into the
        chat with receive_id_type="chat_id".
        """
        content = json.dumps({"text": text}, ensure_ascii=False)

        # Lark message ids start with "om_"; a real thread anchor we can reply
        # to is a message_id. (Native thread_ids start with "omt_" and are not
        # valid reply targets — for those we fall back to a plain chat send.)
        if thread_id and thread_id.startswith("om_"):
            req = (
                ReplyMessageRequest.builder()
                .message_id(thread_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                    .msg_type("text")
                    .reply_in_thread(True)
                    .build()
                )
                .build()
            )
            resp = await self._client.im.v1.message.areply(req)
            if not resp.success():
                logger.error(
                    "LarkAdapter reply failed: code=%s msg=%s log_id=%s",
                    resp.code,
                    resp.msg,
                    resp.get_log_id(),
                )
                return None
            return resp.data.message_id if resp.data else None

        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(channel_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        resp = await self._client.im.v1.message.acreate(req)
        if not resp.success():
            logger.error(
                "LarkAdapter send failed: code=%s msg=%s log_id=%s",
                resp.code,
                resp.msg,
                resp.get_log_id(),
            )
            return None
        return resp.data.message_id if resp.data else None

    async def fetch_file(self, file_ref: FileRef) -> bytes | None:
        """Download a message resource (image/file) via im.v1.message_resource.get.

        Requires the originating message_id. We stash it on FileRef.name? No —
        the message_id is not part of FileRef, so the caller must have it. We
        accept it via FileRef.file_key being prefixed with "<message_id>:<key>"
        when the orchestrator knows the message_id; otherwise we cannot fetch.

        Convention (documented in base.FileRef usage): the orchestrator builds
        the FileRef as `FileRef(file_key="<message_id>|<resource_key>",
        mime="image"|"file")`. We split it here. If no message_id is present we
        return None (Lark resource fetch is impossible without it).
        """
        raw_key = file_ref.file_key or ""
        message_id, _, resource_key = raw_key.partition("|")
        if not resource_key:
            # No message_id prefix supplied; can't address the resource endpoint.
            logger.warning(
                "LarkAdapter.fetch_file: file_key %r missing 'message_id|key' "
                "prefix; cannot fetch Lark resource without a message_id.",
                raw_key,
            )
            return None

        # Lark's resource `type` param: "image" for image messages, "file" for
        # file/audio/media. We carried that hint in FileRef.mime.
        res_type = "image" if (file_ref.mime == "image") else "file"

        req = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(resource_key)
            .type(res_type)
            .build()
        )
        resp = await self._client.im.v1.message_resource.aget(req)
        if not resp.success():
            logger.error(
                "LarkAdapter.fetch_file failed: code=%s msg=%s log_id=%s",
                resp.code,
                resp.msg,
                resp.get_log_id(),
            )
            return None
        # resp.file is a file-like IO[bytes] streamed from the API.
        if resp.file is None:
            return None
        try:
            return resp.file.read()
        except Exception:
            logger.exception("LarkAdapter.fetch_file: failed reading resource body")
            return None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # The lark ws.Client owns an internal reconnect loop; there is no public
        # async stop hook in 1.6.x. Dropping our references + letting the
        # process tear down the socket is the supported path. If a private
        # disconnect exists, best-effort call it.
        client = self._ws_client
        if client is not None:
            for name in ("_disconnect", "disconnect", "_stop", "stop"):
                fn = getattr(client, name, None)
                if callable(fn):
                    try:
                        result = fn()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.debug("LarkAdapter.close: %s() failed", name, exc_info=True)
                    break
