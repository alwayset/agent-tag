"""Local coding-agent CLI backend — coding-plan via YOUR own local CLI.

This backend rents a *locally installed coding-agent CLI* (Claude Code's
`claude` or OpenAI's `codex`) as the harness. It spawns the CLI
non-interactively, streams its stdout back as `Delta`s, and exits. There is no
API client here — the CLI process is the agent loop. The payoff: it runs on
YOUR coding-plan subscription (Claude Pro/Max, ChatGPT/Codex) instead of a
metered API key, so self-hosting your own Agent Tag instance costs nothing
beyond the plan you already pay for.

==============================================================================
⚠️  VENDOR-ToS NOTE — SELF-HOST FOR YOURSELF, NOT A HOSTED BOT FOR OTHERS  ⚠️
==============================================================================
This runs YOUR locally-installed Claude Code / Codex on YOUR coding-plan
subscription. That is fine for self-hosting your own instance — you, on your
own machine, with your own login. The line to know:

  * Anthropic's **Consumer Terms §3.7** ("No automated / scaled use of Claude
    accounts") and the Claude Code usage policy forbid using a *personal
    subscription* to power an automated service that serves OTHER people.
  * OpenAI's terms bind a ChatGPT/Codex plan to a **single End User**; routing
    other people's messages through one Codex login is multi-tenant use of a
    single-seat plan.

So for a HOSTED / multi-tenant bot serving others you must use an API-key
backend instead (`openai` / `OpenAIBackend` or `claude` / `ClaudeApiBackend`),
which is metered, per-seat, and ToS-clean — the Consumer Terms above prohibit
routing others through your subscription. For self-hosting your own instance on
your own coding plan, this backend is a first-class choice.

A one-time runtime note (below) re-states this every process, because a
docstring is easy to skip when you're moving fast.
==============================================================================

Verified CLI flags (2026-06):
  * Claude Code headless: ``claude -p <prompt> --output-format text``
    (or ``--output-format stream-json --verbose --include-partial-messages``
    for incremental token deltas). Docs: https://code.claude.com/docs/en/headless
  * Codex headless: ``codex exec <prompt>`` (prompt is a positional arg; final
    agent message goes to stdout, progress to stderr). ``--json`` switches
    stdout to a JSONL event stream; ``-m/--model`` overrides the model;
    ``--skip-git-repo-check`` allows running outside a git repo.
    Docs: https://developers.openai.com/codex/noninteractive
          https://developers.openai.com/codex/cli/reference
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import warnings
from collections.abc import AsyncIterator

from agent_tag.backends.base import BackendAdapter, Delta, TurnRequest, Usage

logger = logging.getLogger(__name__)

# Emit the ToS warning exactly once per process, no matter how many turns run.
_TOS_WARNING_EMITTED = False

_TOS_WARNING = (
    "CliAcpBackend (backend='cli') shells out to YOUR locally-installed "
    "coding-agent CLI (Claude Code / Codex) on YOUR coding-plan subscription "
    "(Claude Pro/Max, ChatGPT/Codex). That is fine for self-hosting your own "
    "instance — you, your own machine, your own login. For a HOSTED / "
    "multi-tenant bot serving OTHER people, use an API-key backend instead "
    "(backend='openai' or 'claude'): Anthropic Consumer Terms §3.7 ('no "
    "automated/scaled use') and OpenAI's single-End-User binding prohibit "
    "routing others through your subscription."
)


def _emit_tos_warning_once() -> None:
    global _TOS_WARNING_EMITTED
    if _TOS_WARNING_EMITTED:
        return
    _TOS_WARNING_EMITTED = True
    # Both channels: warnings.warn for developers running interactively, and a
    # logger.warning so it shows up in deployed logs (where -W is often off).
    warnings.warn(_TOS_WARNING, UserWarning, stacklevel=2)
    logger.warning(_TOS_WARNING)


class CliAcpBackend(BackendAdapter):
    """Run a local Claude Code / Codex CLI as the agent harness.

    First-class path for self-hosting your own instance on your own coding-plan
    subscription. For a hosted/multi-tenant bot serving others, use an API-key
    backend instead — see the module docstring and the runtime note emitted on
    first use.
    """

    name = "cli"

    def __init__(self, config) -> None:
        self.config = config
        # The executable to invoke, e.g. "claude" or "codex". Comes from
        # Config.cli_command (default "claude").
        self.cli_command: str = getattr(config, "cli_command", None) or "claude"
        self.model: str | None = getattr(config, "model", None)

    # ----- prompt assembly ---------------------------------------------------

    @staticmethod
    def _last_user_message(messages: list[dict]) -> str:
        """Return the content of the most recent user-role message, or ""."""
        for msg in reversed(messages or []):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # content is a plain string per the TurnRequest contract.
                return content if isinstance(content, str) else str(content)
        return ""

    def _build_prompt(self, req: TurnRequest) -> str:
        """Flatten system + last user message into one prompt string.

        The CLI takes a single prompt, so we prepend the system prompt as a
        delimited preamble rather than relying on a separate system channel.
        """
        user_text = self._last_user_message(req.messages)
        system = (req.system or "").strip()
        if system:
            return f"{system}\n\n---\n\n{user_text}"
        return user_text

    def _is_codex(self) -> bool:
        # Match on the basename so "/usr/local/bin/codex" also counts.
        base = self.cli_command.rsplit("/", 1)[-1].lower()
        return base.startswith("codex")

    def _build_argv(self, prompt: str, model: str | None) -> list[str]:
        """Construct the non-interactive argv for the selected CLI.

        We use plain-text output for both CLIs: it is the simplest robust
        contract (incremental stdout = text chunks). stream-json/JSONL parsing
        is intentionally avoided here to keep this dogfood backend dependency-
        and schema-stable.
        """
        if self._is_codex():
            # codex exec <prompt> — prompt is a positional argument; final
            # agent message is printed to stdout, progress goes to stderr.
            argv = [self.cli_command, "exec"]
            if model:
                argv += ["-m", model]
            # Allow running outside a git repo (the bot's CWD may not be one).
            argv += ["--skip-git-repo-check", prompt]
            return argv

        # Claude Code: claude -p <prompt> --output-format text
        argv = [self.cli_command, "-p", prompt, "--output-format", "text"]
        if model:
            argv += ["--model", model]
        return argv

    # ----- turn execution ----------------------------------------------------

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        _emit_tos_warning_once()

        # Fail clearly if the CLI is not on PATH (and not an absolute path).
        if shutil.which(self.cli_command) is None and "/" not in self.cli_command:
            yield Delta(
                type="error",
                text=(
                    f"CLI '{self.cli_command}' not found on PATH. Install the "
                    f"coding-agent CLI (claude / codex) or set cli_command "
                    f"(AGENT_TAG_CLI_COMMAND)."
                ),
            )
            return

        prompt = self._build_prompt(req)
        model = req.model or self.model
        argv = self._build_argv(prompt, model)

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            yield Delta(type="error", text=f"failed to launch '{self.cli_command}': {exc}")
            return

        assert proc.stdout is not None
        assert proc.stderr is not None

        # Drain stderr concurrently so the subprocess never blocks on a full
        # stderr pipe while we read stdout. We surface stderr only if the CLI
        # exits nonzero (otherwise it's just progress chatter, esp. for Codex).
        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            assert proc.stderr is not None
            async for line in proc.stderr:
                stderr_chunks.append(line)

        stderr_task = asyncio.create_task(_drain_stderr())

        try:
            # Read stdout incrementally and yield text chunks as they arrive.
            # readline() gives us natural flush boundaries for text output.
            saw_output = False
            while True:
                chunk = await proc.stdout.readline()
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                if text:
                    saw_output = True
                    yield Delta(type="text", text=text)
        finally:
            # Ensure the process is reaped and stderr fully drained even if the
            # consumer stops iterating early (GeneratorExit) or an error occurs.
            await proc.wait()
            try:
                await stderr_task
            except Exception:  # pragma: no cover - defensive
                pass

        returncode = proc.returncode or 0
        if returncode != 0:
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
            detail = stderr_text or "(no stderr)"
            yield Delta(
                type="error",
                text=f"'{self.cli_command}' exited with code {returncode}: {detail}",
                data={"returncode": returncode, "argv": argv[:2]},
            )
            return

        if not saw_output:
            # Clean exit but empty stdout — surface as an error so the caller
            # doesn't post a blank reply.
            yield Delta(
                type="error",
                text=f"'{self.cli_command}' produced no output (exit 0).",
            )
            return

        yield Delta(type="done")

    # ----- usage -------------------------------------------------------------

    def report_usage(self) -> Usage:
        # The plain-text CLI output carries no token accounting. (stream-json /
        # `codex exec --json` expose usage, but we don't parse those here.)
        return Usage()
