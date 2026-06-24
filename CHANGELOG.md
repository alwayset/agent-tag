# Changelog

All notable changes to Agent Tag are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-06-24

Launch-readiness pass; first verified production run.

### Added
- **Supervised service** — `agent-tag service install/uninstall/status` registers a
  keep-alive launchd agent (macOS) or emits a systemd unit (Linux) so the bot runs
  at login and restarts on crash, surviving reboots.
- **Dedicated Lark custom-app path verified end-to-end** — a published custom app
  connects over a WebSocket long-connection and answers real DMs/@-mentions grounded
  in the ingested wiki, independent of any other bot.
- **PyPI packaging** — release-triggered `publish.yml` (OIDC trusted publishing), `RELEASING.md`.
- **Launch assets** — `docs/launch.md` (Show HN + thread), `docs/comparison.md` (vs Claude Tag).
- Test suite expanded to **70 tests** (orchestrator, settings, store, ingest, Lark helpers).

### Fixed
- **Lark adapter / lark-oapi embedding** — the SDK's module-level event loop (captured
  at import = the host app's main loop) collided with `run_until_complete`. The WS
  client is now constructed and started on a worker thread with a fresh loop repointed
  via the module global, so the long-connection works inside an async app.

## [0.1.0] — 2026-06-24

First public release. An open, self-hosted, agent-agnostic AI teammate that lives
in your group chats — Lark-first, with Slack and Discord adapters.

### Added
- **Shared teammate** — one identity the whole channel collaborates with, keyed by
  `(platform, channel_id)` rather than per-user.
- **Per-channel isolated memory** — a capability-fenced namespace where the
  agent-facing memory tool cannot read or write across channels.
- **Corpus ingestion** — crawl your Lark wiki (spaces → nodes → docx) via `lark-cli`,
  index it into SQLite **FTS5**, and blend retrieval into every reply, with citations.
  `agent-tag lark-spaces` / `agent-tag ingest --space <id>`.
- **Governance** — per-channel tool allowlist, token budgets with a kill-switch,
  an append-only audit log, and best-effort outbound redaction (DLP).
- **Ambient mode** — opt-in, deterministic per-channel follow-up nudges.
- **Admin web console** — connections, workspace/users, channels, knowledge,
  memory, audit, and usage pages (FastAPI + Jinja2, no build step).
- **Any model** — backends for the Anthropic API, OpenAI API, and your local
  Claude Code / Codex CLI on a coding-plan subscription (self-host only; hosted
  multi-tenant use must use an API key).
- **Adapters** — Lark via `lark-cli` (`larkcli`) and via a custom app (`lark`),
  plus Slack and Discord; a `console` adapter for a zero-credential local demo.
- **Persistence** — a single-file SQLite store (default), zero infrastructure.
- **Deploy** — `Dockerfile` + `docker-compose.yml`, one-command `docker compose up`.

[Unreleased]: https://github.com/alwayset/agent-tag/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/alwayset/agent-tag/releases/tag/v0.2.0
[0.1.0]: https://github.com/alwayset/agent-tag/releases/tag/v0.1.0
