# Security Policy

## Supported versions

Agent Tag is pre-1.0. Security fixes land on the latest `0.1.x` release.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately through either channel:

- **GitHub Security Advisories** (preferred) —
  <https://github.com/alwayset/agent-tag/security/advisories/new>. This opens a
  private advisory only the maintainers can see.
- **Email** — **security@agenttag.dev**.

Please include enough detail to reproduce: affected version/commit, deployment
mode (Docker / pip), adapter and backend in use, and a proof-of-concept if you
have one.

## Scope

Agent Tag is **self-hosted and bring-your-own-key**. You run the process, you
hold the database, and you supply the model credentials (an Anthropic/OpenAI API
key, or a local coding-CLI session). There is no Agent Tag-operated server or
hosted service in the trust boundary — so operational security of *your*
deployment (host, network exposure, the SQLite database file, the admin token,
the secrets in your `.env`) is yours to manage. See
[`docs/deploy.md`](docs/deploy.md) for the admin token and exposure guidance.

In scope for this policy — vulnerabilities **in the Agent Tag code**, for
example:

- Cross-channel leakage that breaks the **memory-isolation fence** (see below).
- Bypasses of governance controls: per-channel tool allowlist, token
  budgets / kill-switch, or the append-only audit log.
- Failures of the outbound **redaction / DLP** path that leak data the operator
  configured to be redacted.
- Admin-console authentication/authorization bypass, injection, SSRF, or path
  traversal.
- Secret/credential disclosure (API keys, Lark app secret, admin token) via the
  process, logs, or the database.

### Key security property: the memory-isolation fence

Each channel gets **isolated memory**. The fence is structural: the agent's
memory tool exposes **no namespace parameter**, so a turn in one channel cannot
read or write another channel's notes
(`agent_tag/core/memory.py`, exercised by
`tests/test_memory_isolation.py`). A way to make memory cross that fence — to read
or write another channel's notes — is the highest-severity class of bug for this
project. Report it privately.

### Coding-plan CLI backend — ToS caveat (not a vulnerability)

The optional `cli` backend shells out to a local **Claude Code** / **Codex** CLI
that is already logged in on the host. Agent Tag ships **no billing code** and is
BYO **metered API key**; it does not reuse "included" subscription tokens.
Powering a shared, multi-user, automated bot off a Claude (Max/Team) or
OpenAI/ChatGPT **subscription seat** is prohibited by both vendors' terms, so the
`cli` backend is labeled **personal dogfooding only** in the console. This is a
terms-of-service constraint, **not** a security vulnerability — please don't file
it as one. For production, use the BYO-API-key backends (`claude` / `openai`).

### Out of scope

- Vulnerabilities in third-party dependencies (report upstream; we will bump once
  a fix is released).
- Issues that require a compromised host, a malicious operator, or a leaked admin
  token to exploit.
- Misconfiguration of your own deployment (e.g. binding the console to a public
  interface without an admin token, committing a `.env` with live secrets).
- The coding-plan ToS caveat described above.

## Response expectations

This is a small open-source project maintained on a best-effort basis. We aim to:

- **Acknowledge** your report within **3 business days**.
- Provide an initial **assessment** within **7 business days**.
- Keep you updated on remediation and coordinate a disclosure timeline with you.

We practice coordinated disclosure: please give us a reasonable window to ship a
fix before any public write-up. We are happy to credit reporters in the advisory
unless you prefer to remain anonymous.
