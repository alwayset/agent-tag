"""ConsoleAdapter — a local, zero-credentials adapter so you can drive the whole
system from a terminal. Simulate different users and channels to see the shared
teammate keep per-channel isolated memory across an organization.

Commands:
  /user <name>      switch who is speaking
  /channel <name>   switch channel
  /who              show current user + channel
  /help             show commands
  /quit             exit
Any other line is a message (treated as @-mentioning the bot).
"""
from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator

from agent_tag.adapters.base import Adapter, InboundEvent

BANNER = """\
Agent Tag — console mode. Type a message (it @-mentions the teammate).
  /user <name>  /channel <name>  /who  /help  /quit
Currently: user=you  channel=general
"""

HELP = """\
  /user <name>     switch who is speaking (e.g. /user alice)
  /channel <name>  switch channel        (e.g. /channel eng-help)
  /who             show current user + channel
  /help            show this
  /quit            exit
"""


class ConsoleAdapter(Adapter):
    platform = "console"

    def __init__(self, config=None) -> None:  # config unused; kept for registry uniformity
        self._user = "you"
        self._channel = "general"
        self._seq = 0

    def _cmd(self, line: str) -> bool:
        """Handle a /command. Return False to stop the stream."""
        parts = line.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "/quit":
            return False
        if cmd == "/help":
            print(HELP)
        elif cmd == "/who":
            print(f"  user={self._user}  channel={self._channel}")
        elif cmd == "/user" and arg:
            self._user = arg
            print(f"  → now speaking as '{self._user}'")
        elif cmd == "/channel" and arg:
            self._channel = arg
            print(f"  → now in channel '{self._channel}'")
        else:
            print(f"  (unknown or incomplete command: {line!r}) — try /help")
        return True

    async def stream_inbound(self) -> AsyncIterator[InboundEvent]:
        loop = asyncio.get_event_loop()
        print(BANNER, end="")
        while True:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, KeyboardInterrupt):
                break
            if line == "":  # EOF (piped input exhausted / ctrl-D)
                break
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("/"):
                if not self._cmd(line):
                    break
                continue
            self._seq += 1
            yield InboundEvent(
                platform=self.platform,
                channel_id=self._channel,
                user_id=self._user,
                user_display_name=self._user,
                text=line,
                mentions_bot=True,
                message_id=f"console-{self._seq}",
            )

    async def send(self, channel_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        print(f"\n🤖 [#{channel_id}] {text}\n")
        return None
