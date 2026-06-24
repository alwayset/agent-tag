"""LarkCliAdapter — the smooth Lark path: ride the `lark-cli` binary.

Inbound:  `lark-cli event +subscribe` (WebSocket long-connection, NDJSON to stdout)
Outbound: `lark-cli im +messages-send` (bot identity)

Because lark-cli is already authorized (the operator did its click-a-link OAuth
once), there is no app-scope wiring to do here. Note lark-cli's event subscription
holds a single-instance lock — don't run another lark-cli event consumer alongside.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from agent_tag.adapters.base import Adapter, InboundEvent
from agent_tag.lark_cli import find_lark_cli

_MENTION_RE = re.compile(r"@_(user_\d+|all)\b")


def _extract_text(message: dict) -> str:
    raw = message.get("content") or ""
    try:
        content = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        return raw if isinstance(raw, str) else ""
    text = content.get("text")
    if text is None and "content" in content:  # post/rich — best-effort flatten
        try:
            parts = []
            for block in content.get("content", []):
                for seg in block:
                    if isinstance(seg, dict) and seg.get("text"):
                        parts.append(seg["text"])
            text = " ".join(parts)
        except Exception:  # noqa: BLE001
            text = ""
    text = text or ""
    return _MENTION_RE.sub("", text).strip()


class LarkCliAdapter(Adapter):
    platform = "lark"

    def __init__(self, config=None) -> None:
        self.config = config
        self.cli = find_lark_cli(config)
        self._proc: asyncio.subprocess.Process | None = None

    def _normalize(self, evt: dict) -> InboundEvent | None:
        header = evt.get("header", {}) or {}
        etype = header.get("event_type") or evt.get("event_type")
        if etype and etype != "im.message.receive_v1":
            return None
        body = evt.get("event", evt) or {}
        message = body.get("message", {}) or {}
        if not message.get("chat_id"):
            return None
        sender = (body.get("sender", {}) or {}).get("sender_id", {}) or {}
        chat_type = message.get("chat_type", "")
        mentions = message.get("mentions") or []
        return InboundEvent(
            platform=self.platform,
            channel_id=message.get("chat_id", ""),
            user_id=sender.get("open_id", "") or sender.get("user_id", ""),
            text=_extract_text(message),
            mentions_bot=(chat_type == "p2p") or bool(mentions),
            thread_id=message.get("thread_id") or message.get("root_id"),
            message_id=message.get("message_id"),
            raw=evt,
        )

    async def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        if not self.cli:
            raise RuntimeError("lark-cli not found; install it or set LARK_CLI_PATH")
        self._proc = await asyncio.create_subprocess_exec(
            self.cli,
            "event",
            "+subscribe",
            "--as",
            "bot",
            "--event-types",
            "im.message.receive_v1",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert self._proc.stdout is not None
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if not s or s[0] != "{":
                continue
            try:
                evt = json.loads(s)
            except json.JSONDecodeError:
                continue
            norm = self._normalize(evt)
            if norm and norm.text:
                yield norm

    async def send(self, channel_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        if not self.cli:
            return None
        proc = await asyncio.create_subprocess_exec(
            self.cli,
            "im",
            "+messages-send",
            "--as",
            "bot",
            "--chat-id",
            channel_id,
            "--text",
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return None

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass
