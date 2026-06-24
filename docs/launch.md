# Launch assets

Copy for launching Agent Tag. Honest, technical, founder voice. No fabricated metrics.

- Repo: <https://github.com/alwayset/agent-tag>
- Landing: <https://alwayset.github.io/agent-tag>
- Contact: hello@agenttag.dev · Maintainer: Sha Tao ([@alwayset](https://github.com/alwayset))

---

## Show HN

**Title:**

> Show HN: Agent Tag – an open, self-hosted alternative to Claude Tag that reads your Lark wiki

**Body:**

I built an open, self-hosted alternative to Claude Tag (Anthropic's `@`-mentionable Slack
teammate, which they shipped yesterday as the successor to Claude-in-Slack). Agent Tag is the
same shape — one bot the whole channel `@`-mentions — but open-source (Apache-2.0), runs on
any model, is Lark-first (Slack and Discord adapters too), and indexes your existing docs so
replies are grounded in and cited from your own wiki.

The reason I started it: my team lives in Lark, not Slack, and the thing I actually wanted
wasn't "a chat model in a channel" — it was a teammate that already knows our internal docs.
So the core feature is corpus ingestion: it crawls your Lark wiki (spaces → nodes → docx) via
the official `lark-cli`, chunks and indexes the text into SQLite **FTS5**, and on each reply
retrieves the relevant chunks, blends them into context, and cites the source doc by title.

Where it stands: a dedicated Agent Tag Lark app (its own bot) connects over a WebSocket long
connection and is serving a real group. I asked it in a DM, *"What's our YouTube/Google API
auth compliance policy?"* and it answered from our ingested wiki and cited the doc — instead
of guessing. That grounded loop is the whole point of the project.

How it's built:
- **One Python process, one SQLite file.** Core runs on the stdlib; adapters/backends pull
  their own extras. `pip install -e '.[all]'` or `docker compose up`.
- **Adapters** normalize each platform (Lark via `lark-cli` or a custom app over WebSocket;
  Slack; Discord; plus a `console` adapter for a zero-credential local demo) into one
  `InboundEvent` + `send`.
- **Backends** sit behind one seam: Anthropic API, OpenAI API, or your local Claude Code /
  Codex CLI. Bring your own key. (A coding-plan/subscription seat is for personal dogfooding
  only — powering a shared, hosted bot off one violates Anthropic's and OpenAI's terms, so the
  console labels that backend as such.)
- **Per-channel memory is capability-fenced** — the agent-facing memory tool has no namespace
  argument, so one channel literally can't read or write another's notes.
- **Governance**: per-channel tool allowlist, token budgets with a kill-switch, an append-only
  audit log, and best-effort outbound redaction (DLP). All edited in an admin web console; no
  config files to hand-edit.
- **Honest about limits**: corpus ingestion currently reads docx/doc nodes and reports
  sheets/bitable/mindnote/files as skipped (more readers are a TODO). Redaction is
  best-effort defense-in-depth, not a guarantee. Some Lark *international* tenants don't expose
  long-connection events, which the custom-app adapter needs.

Status: beta (v0.1.0). CI is green — ruff plus a pytest matrix on 3.11 / 3.12 / 3.13. It runs
end-to-end today, but interfaces may still change before 1.0.

I'd love feedback on the adapter/backend extension surface (the two SDK seams) and on the
governance model. Repo: https://github.com/alwayset/agent-tag — Apache-2.0, Python 3.11+.

A short comparison with Claude Tag is in the repo at docs/comparison.md, including what Claude
Tag does better (zero ops, first-party Claude, maturity).

---

## X thread

**1/**
Anthropic shipped Claude Tag yesterday — an `@`-mentionable Claude teammate for Slack.

I built the open alternative: Agent Tag. Self-hosted, Apache-2.0, runs on any model, Lark-first
(Slack + Discord too), and it reads your existing wiki.

https://github.com/alwayset/agent-tag

**2/**
The wedge is grounding in YOUR docs.

Agent Tag crawls your Lark wiki, indexes it into SQLite FTS5, and on every reply retrieves the
right chunks and cites the source doc by title.

Not "a model in a channel" — a teammate that already knows your internal docs.

**3/**
It's live. A dedicated Agent Tag Lark bot (its own app) connects over a WebSocket long
connection. I DM'd it:

"What's our YouTube/Google API auth compliance policy?"

It answered from our ingested wiki and cited the doc — instead of guessing.

**4/**
Under the hood: one Python process, one SQLite file.

• Adapters: Lark / Slack / Discord / console
• Backends behind one seam: Anthropic API, OpenAI API, or your local Claude Code / Codex CLI (BYO key)
• Per-channel memory, capability-fenced — channels can't read each other
• Allowlist + token budgets + audit log + redaction

**5/**
Status: beta (v0.1.0). CI green — ruff + pytest on 3.11/3.12/3.13.

If your team lives in Lark and you want a self-hosted teammate grounded in your own docs, try
it. Apache-2.0, feedback welcome.

Repo → https://github.com/alwayset/agent-tag
hello@agenttag.dev
