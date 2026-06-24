# Agent Tag

> ⚠️ Working name. Open, **agent-agnostic**, **platform-agnostic** AI teammate that lives in a group chat — a self-hostable answer to the "AI teammate in your channel" pattern, for **Lark / Slack / Discord**, on **any model**.

Agent Tag is **not** a coding-agent bridge ("control my CLI from chat"). It's a shared teammate that a whole team `@`-mentions, that keeps **per-channel isolated memory**, and that admins can **govern** — built on a harness you *rent* (Claude / Codex / any ACP agent), not one it reimplements.

## Status

**MVP walking skeleton.** Runs end-to-end *today* with zero credentials via a console adapter + echo backend. Platform adapters (Lark/Slack/Discord) and real model backends (Claude/Codex) are scaffolded against locked interfaces and need credentials to live-test. The headline differentiator — **ingesting + indexing your existing corpus** (Lark wiki / Google Drive / Notion) — is the next milestone, tracked in [`TODO.md`](TODO.md).

## Quickstart

Two ways to stand up the admin console at **http://localhost:8765**. Pick one.

### (a) Docker — `docker compose up`

```bash
cp .env.example .env      # creates the env file compose reads (defaults are fine to start)
docker compose up         # builds the image, starts the runtime + admin console
```

Open **http://localhost:8765**. The SQLite database (settings, memory, audit) persists in a named Docker volume across restarts.

### (b) pip — `agent-tag serve`

Requires Python 3.11+.

```bash
pip install -e '.[all]'   # web admin console + all chat adapters + all LLM backends
agent-tag serve           # admin console on 127.0.0.1:8765 (use --host 0.0.0.0 to expose)
```

Open **http://localhost:8765**.

### Then: configure from the console

The admin console is the control plane — no config files to hand-edit. The flow:

1. **Connections** — enter your Lark credentials (App ID / App Secret / domain) and pick a **backend** (the LLM that powers replies). See [backend modes](#backend-modes) below.
2. **Workspace** — bind your Lark group: the bot auto-enrolls users when they first `@`-mention it, so one teammate serves the whole group.
3. **Chat** — `@`-mention the bot in the bound group. It replies with per-channel isolated memory and governed tools.

> Connection changes take effect on the **next `serve` start** — the console shows a reminder. After editing Connections, restart the process (`docker compose restart` or re-run `agent-tag serve`) to (re)bind adapters.

For Lark app creation (scopes, bot, long-connection events, adding the bot to a group), see **[`docs/lark-setup.md`](docs/lark-setup.md)**. For deployment, env vars, the admin token, and backups, see **[`docs/deploy.md`](docs/deploy.md)**.

### Recommended Lark setup — Lark CLI

There are **two Lark adapters**, selected by `AGENT_TAG_ADAPTER` (or the
**Enabled chat platforms** field in the console):

| Adapter | What it is | When to use |
|---------|-----------|-------------|
| **`larkcli`** (recommended, smooth) | Rides the official [Lark CLI](https://github.com/larksuite/cli) — you authorize once with a click-a-link OAuth and Agent Tag shells out to the `lark-cli` binary for events, sending, and the corpus crawl. No app scopes to hand-configure. | The fast path for most setups. |
| **`lark`** (advanced) | A custom Lark app via the `lark-oapi` SDK over a WebSocket long connection. You create the app, add scopes, and publish a version yourself. | Containerized / headless deploys, or when you can't run the `lark-cli` binary on the host. |

The smooth path:

```bash
npm install -g @larksuite/cli   # or build/install per the lark-cli README
lark-cli config init            # one-time: enter app credentials
lark-cli auth login             # opens a click-to-authorize link in your browser
```

Then point Agent Tag at it and start the runtime:

```bash
export AGENT_TAG_ADAPTER=larkcli   # or set "Enabled chat platforms" = larkcli in the console
agent-tag serve
```

`lark-cli` stores its auth in `~/.lark-cli/`; Agent Tag reads that to act as you.

> **Single-instance event lock.** The `larkcli` adapter consumes the Lark event
> stream through `lark-cli`. Don't run a **second** `lark-cli` event consumer
> (another `agent-tag serve`, or a separate `lark-cli` long-connection session)
> against the same auth at the same time — only one consumer should hold the
> event stream, or events will be split/dropped.

### Knowledge base (ingest your Lark wiki)

Agent Tag can ingest and index your existing **Lark wiki** so the teammate
answers from your corpus. This rides the same `lark-cli` auth as the `larkcli`
adapter, so authorize Lark CLI first (above).

```bash
agent-tag lark-spaces                 # list your Lark wiki spaces (space_id + name)
agent-tag ingest --space <space_id>   # crawl + index one space into the knowledge base
```

The admin console also has a **Knowledge** page showing what's indexed (docs,
chunks, sources) and lets you ingest a space from the browser.

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
what did alice say about deploy?      # bob, same channel → shared teammate sees it
/channel sales
what did alice say about deploy?      # different channel → isolated, nothing leaks
```

## Backend modes

A *backend* is the LLM harness Agent Tag rents to produce replies. Two ways to power it:

| Mode | How | Use it for |
|------|-----|-----------|
| **BYO API key** (recommended) | Set an `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) in Connections; pick backend `claude` or `openai`. | Production. A real metered API key billed per token. |
| **Coding-plan via local CLI** | Pick backend `cli`; Agent Tag shells out to a local **Claude Code** / **Codex** CLI already logged in on the host. | **Personal dogfooding only.** |

> **ToS note.** Agent Tag ships **no billing code** and is **BYO metered API key**. It does **not** reuse "included" subscription / coding-plan tokens: powering a shared, multi-user, automated bot off a Claude (Max/Team) or OpenAI/ChatGPT subscription seat is prohibited by both vendors (Anthropic Consumer Terms §3.7 "OpenClaw" rule; OpenAI single-End-User). The local-CLI backend exists for **personal dogfooding only** and is labeled as such in the console.

To smoke-test wiring without any LLM, use backend `echo` (parrots input).

## Architecture

```
IM (Lark/Slack/Discord/console)  ──Adapter──►  Agent Tag Core  ──BackendAdapter(ACP)──►  Claude / Codex / any agent
                                                   │
                          Router → Workspace/Org/User → ChannelPolicy → Orchestrator
                          (single-writer lock + idempotency) → namespace-fenced Memory
                          → Redaction/DLP → send;  append-only Audit
```

- **Adapter** (`agent_tag/adapters/`) — one chat platform → normalized `InboundEvent` + `send`.
- **BackendAdapter** (`agent_tag/backends/`) — rent a harness; stay model-agnostic behind one seam.
- **WorkspaceService** (`agent_tag/workspace/`) — Organization → Workspace → Channel; users auto-enroll on first `@`, so one teammate serves a whole org.
- **Memory** (`agent_tag/core/memory.py`) — distilled notes, **capability-fenced per channel**: the agent's memory tool has no namespace parameter, so it cannot read/write across channels.
- **Orchestrator** (`agent_tag/core/orchestrator.py`) — assembles identity + memory, drives the backend, redacts, audits.

## License

[Apache-2.0](LICENSE). Contributions welcome — the `Adapter` and `BackendAdapter` SDKs are the extension surface.
