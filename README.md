# Agent Tag

**An open, self-hosted AI teammate that lives in your group chat — Lark-first, on any model, grounded in your own docs.**

[![CI](https://github.com/alwayset/agent-tag/actions/workflows/ci.yml/badge.svg)](https://github.com/alwayset/agent-tag/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Agent Tag is a shared teammate that a whole team `@`-mentions in a group chat. It keeps **per-channel isolated memory**, answers from **your existing knowledge base** (it ingests and indexes your Lark wiki), and gives admins real **governance** — a per-channel tool allowlist, token budgets, an append-only audit log, and outbound redaction.

The wedge vs Anthropic's "Claude Tag": Agent Tag is **open** (Apache-2.0) and **self-hosted**, runs on **any model** (bring your own Anthropic/OpenAI key, or your local Claude Code / Codex CLI), is **Lark-first** (Slack and Discord adapters too), and **reads your existing docs** instead of starting from an empty context — none of which Claude Tag does.

📖 **Landing page & docs:** <https://alwayset.github.io/agent-tag>

## Features

- **Multiplayer shared teammate** — one bot serves a whole group; users auto-enroll when they first `@`-mention it.
- **Per-channel isolated memory** — distilled notes are capability-fenced per channel; the memory tool has no namespace parameter, so the agent cannot read or write across channels.
- **Corpus ingestion** — crawl and index your existing **Lark wiki** into a SQLite + FTS5 store so replies are grounded in your real docs.
- **Governance** — per-channel tool allowlist, per-channel token budgets with a kill-switch, an append-only audit log, and best-effort outbound redaction/DLP.
- **Ambient nudges** — a deterministic, opt-in, time-based proactive scheduler (no hidden LLM gate); content is suppressed when the model returns `SKIP`.
- **Admin web console** — the control plane for connections, workspaces, knowledge, and governance. No config files to hand-edit.
- **Any model** — backends for the Anthropic and OpenAI APIs (BYO metered key), plus a local coding-plan CLI backend (Claude Code / Codex) for personal dogfooding.
- **Self-hosted, Apache-2.0** — a single Python process and one SQLite file. Your data and keys never leave your host.

## Quickstart

Two ways to stand up the admin console at **http://localhost:8765**. Pick one.

### Docker

```bash
cp .env.example .env      # compose reads this; defaults are fine to start
docker compose up         # builds the image, starts the runtime + admin console
```

The SQLite database (settings, memory, audit) persists in a named Docker volume across restarts.

### pip

Requires Python 3.11+.

```bash
pip install -e '.[all]'   # web console + all chat adapters + all LLM backends
agent-tag serve           # admin console on http://localhost:8765
```

### Zero-credential demo

No accounts, no keys — chat with the teammate in your terminal and watch per-channel memory stay isolated:

```bash
agent-tag run --adapter console --backend echo
```

```
/user alice
/channel eng-help
our staging deploy uses the deploy-staging workflow
/user bob
what did alice say about deploy?      # same channel → the shared teammate sees it
/channel sales
what did alice say about deploy?      # different channel → isolated, nothing leaks
```

## Onboard your org on Lark

Five steps — the smooth path rides the official [Lark CLI](https://github.com/larksuite/cli), so there are no app scopes to hand-configure. Full walkthrough in [`docs/lark-setup.md`](docs/lark-setup.md).

1. **Install** — get Agent Tag and the Lark CLI, the whole toolchain:
   ```bash
   pip install -e '.[all]'
   npm install -g @larksuite/cli
   ```
2. **Authorize Lark** — run one command, click the link it prints, approve in your browser. That's the consent:
   ```bash
   lark-cli config init    # one-time: enter app credentials
   lark-cli auth login     # opens a click-to-authorize link
   ```
3. **Connect a model** — start the runtime and set your backend once in the console:
   ```bash
   export AGENT_TAG_ADAPTER=larkcli
   agent-tag serve         # open http://localhost:8765 → Connections
   ```
4. **Ingest your knowledge** — index a Lark wiki space so the teammate answers from your real docs (or do it from the console's **Knowledge** page):
   ```bash
   agent-tag lark-spaces                 # list your wiki spaces (space_id + name)
   agent-tag ingest --space <space_id>   # crawl + index one space
   ```
5. **Go live** — add the bot to a Lark group and `@`-mention it. Anyone in the channel can ask; it replies in the thread, grounded in your knowledge and per-channel memory.

> **Coding-plan vs API key (ToS).** For a shared, multi-user, hosted bot, use a **BYO metered API key** (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, backend `claude` / `openai`). Powering a shared bot off a subscription / coding-plan seat is prohibited by both Anthropic (Consumer Terms §3.7) and OpenAI, so the local-CLI backend (`cli`, your logged-in Claude Code / Codex) is for **personal dogfooding only** and is labeled as such in the console.

## Architecture

```
IM (Lark / Slack / Discord / console)
        │  Adapter  → normalized InboundEvent + send
        ▼
   Agent Tag Core
     Router → Workspace / Org / User → ChannelPolicy → Orchestrator
     (single-writer lock + idempotency)
       ├─ capability-fenced Memory (per channel)
       ├─ Governance: tool allowlist · token budget · audit · redaction/DLP
       └─ Corpus retrieval (SQLite + FTS5)
        │  BackendAdapter
        ▼
   Backend: Claude API · OpenAI API · local coding-plan CLI (ACP) · echo
```

- **Transport (adapters)** normalize each chat platform into an `InboundEvent` and a `send`. Lark rides the official `lark-cli` binary (smooth path) or the `lark-oapi` SDK over a WebSocket long connection (custom-app path).
- **Core** routes the turn through policy, memory, governance, and the orchestrator under a single-writer lock.
- **Backend adapters** keep the system model-agnostic behind one seam — Anthropic/OpenAI HTTP APIs, a local CLI over ACP, or `echo` for wiring tests.
- **Store** is one SQLite file: settings, per-channel memory, audit log, token usage, and the FTS5-indexed corpus.

## Configuration

Connection **credentials** (Lark/Slack/Discord tokens, backend API keys, active backend/model) are set in the **admin console** and stored in the database — you don't need them in the environment. The env vars below are infra-level settings read at process start.

| Setting | Where | Default | Purpose |
|---------|-------|---------|---------|
| `AGENT_TAG_DB` | env | `agent_tag.db` | SQLite database path (Docker uses `/data/agent_tag.db`). |
| `AGENT_TAG_WEB_HOST` | env | `127.0.0.1` | Admin console bind host (`0.0.0.0` to expose). |
| `AGENT_TAG_WEB_PORT` | env | `8765` | Admin console port. |
| `AGENT_TAG_ADMIN_TOKEN` | env | _(unset)_ | If set, the console requires this token. **Set it whenever the console is reachable beyond localhost.** |
| `AGENT_TAG_ADAPTER` | env / console | `console` | First chat platform to run: `larkcli` · `lark` · `slack` · `discord` · `console`. |
| `AGENT_TAG_BACKEND` | env / console | `echo` | Default backend: `claude` · `openai` · `cli` · `echo`. |
| Backend keys | console | — | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, or `AGENT_TAG_CLI_COMMAND` (`claude`/`codex`). |
| Tool allowlist · token budget · ambient · redaction | console | — | Per-channel governance, edited in the console (`AGENT_TAG_REDACTION=0` disables redaction globally). |

The CLI flags `--host / --port / --db / --token` override the corresponding env vars. See [`docs/deploy.md`](docs/deploy.md) for the admin token, backups, and containerized notes.

## Security & privacy

- **Memory fence** — per-channel memory is capability-fenced: the agent's memory tool exposes no namespace argument, so one channel's notes can't leak into another.
- **Redaction (best-effort)** — outbound replies pass through a best-effort redaction/DLP pass (on by default, `AGENT_TAG_REDACTION`). Treat it as defense-in-depth, not a guarantee.
- **Self-hosted, BYO key** — Agent Tag ships no billing code and never phones home; your data and model credentials stay on your host.
- **Admin console** — has no auth by default and is meant to sit on `127.0.0.1`. If you expose it, set `AGENT_TAG_ADMIN_TOKEN` and front it with HTTPS.

Found a vulnerability? Please report it privately — see [`SECURITY.md`](SECURITY.md).

## Contributing

Contributions welcome — the `Adapter` and `BackendAdapter` SDKs are the extension surface. Run `pytest` for tests and `ruff check` / `ruff format` for lint and formatting. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE).

## Status

**Beta (0.1.0).** Runs end-to-end today; interfaces may still change before 1.0.
