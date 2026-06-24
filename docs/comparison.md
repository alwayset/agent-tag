# Agent Tag vs Claude Tag

Anthropic launched **Claude Tag** on **2026-06-23** as the successor to Claude-in-Slack
— an `@`-mentionable Claude teammate for Slack channels. Agent Tag covers the same
"shared AI teammate in your group chat" shape, but takes the open, self-hosted route and
adds query-time grounding in your own documentation.

This page is an honest side-by-side. Where Claude Tag's behavior is described, it reflects
its public positioning as of its 2026-06-23 launch; check Anthropic's docs for the current
state, since a hosted product can change.

| | **Agent Tag** | **Claude Tag** |
|---|---|---|
| **Open-source / self-host** | Yes — Apache-2.0, runs as one Python process + one SQLite file on your host | No — hosted, managed by Anthropic |
| **Any model** | Yes — Anthropic API, OpenAI API, or a local Claude Code / Codex CLI (BYO key) | No — Claude-only |
| **Chat platforms** | Lark (first-class), Slack, and Discord adapters | Slack-only |
| **Indexes your existing docs** | Yes — crawls and indexes your Lark wiki into a local FTS5 store, then cites the source on every grounded reply | No — relies on query-time connectors, not a pre-built index of your docs |
| **Per-channel memory** | Yes — capability-fenced; the memory tool has no namespace argument, so one channel can't read another's notes | Yes — per-channel memory |
| **Governance** | Yes — per-channel tool allowlist, token budgets with a kill-switch, append-only audit log, best-effort outbound redaction | Yes — admin governance over a managed service |
| **Pricing** | Self-host, bring-your-own model key (no per-seat fee from us) | Enterprise plan |

## What this means in practice

- **Self-host & data residency.** Agent Tag ships no billing code and never phones home.
  Your chat data, memory, audit log, and model credentials stay on the host you run it on.
  Claude Tag is a managed service — your messages flow through Anthropic's hosted product.

- **Model choice.** Agent Tag is model-agnostic behind one `BackendAdapter` seam: point it
  at the Anthropic API, the OpenAI API, or a local coding-plan CLI (Claude Code / Codex) for
  personal dogfooding. Claude Tag runs on Claude.

- **Lark-first.** Agent Tag was built Lark-first (via the official `lark-cli` or a custom app
  over a WebSocket long connection), with Slack and Discord adapters alongside. Claude Tag is
  Slack-only today. If your team lives in Lark/Feishu, Agent Tag meets you there.

- **Grounding in your own docs.** This is the sharpest difference. Agent Tag ingests your
  Lark wiki ahead of time, indexes it locally, and on each reply retrieves the relevant
  chunks and cites the source doc by title. Claude Tag answers from the model plus query-time
  connectors, not from a pre-built index of your documentation.

## What Claude Tag does better

Being fair cuts both ways:

- **Zero ops.** Claude Tag is fully managed — nothing to deploy, patch, or keep running.
  Agent Tag is a process *you* operate.
- **First-party Claude.** If you're standardized on Claude and Slack, Claude Tag is the
  native, supported path straight from Anthropic.
- **Maturity.** Claude Tag is a shipped commercial product. Agent Tag is beta (v0.1.0) —
  interfaces may still change before 1.0.

If you want a managed, Claude-on-Slack teammate, Claude Tag is the straight answer. If you
want to **self-host**, run **any model**, work in **Lark** (or Slack/Discord), and have
replies **grounded in and cited from your own wiki** — that's where Agent Tag fits.

— Maintainer: Sha Tao ([@alwayset](https://github.com/alwayset)) · <hello@agenttag.dev>
