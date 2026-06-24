# Agent Tag — Roadmap / TODO

Status legend: `[ ]` not started · `[~]` partial/scaffolded · `[x]` done

## ✅ v1 (this build — usable end-to-end)
- [x] Org → Workspace → Channel → multi-user model (auto-enroll, cross-platform identity)
- [x] **Persistent SqliteStore** (one file, survives restart — the memory entity persists)
- [x] `Adapter` seam: **console** (runnable) + **Lark / Slack / Discord** (SDK-verified; need creds)
- [x] `BackendAdapter` seam: **echo** + **Claude API** + **OpenAI API** + **coding-plan local CLI** (Claude Code / Codex)
- [x] TurnOrchestrator: per-channel single-writer lock + idempotency + capability-fenced memory
- [x] **Token metering + per-channel budget kill-switch**
- [x] **Deterministic ambient** scheduler (opt-in, interval-gated, backend-generated, SKIP-aware)
- [x] Outbound redaction/DLP + append-only audit
- [x] **Admin web UI**: dashboard/setup checklist · connections · workspace/users · channel policy editor · **memory dashboard (view/edit/delete)** · audit · usage · optional token auth
- [x] **`agent-tag serve`** = web console + adapters + ambient in one process
- [x] **Easy deploy**: Dockerfile + `docker compose up` + `.env` + README quickstart + Lark setup guide
- [x] BYO-API-key; coding-plan via your own local CLI (self-host); **no billing code, no subscription-token reuse for hosted**
- [x] 21 passing tests (store/memory-fence/settings/budget/ambient/orchestrator); web smoke-tested via TestClient + live `serve`

### Claude Tag feature parity — where v1 stands
- ✅ multiplayer shared identity · ✅ per-channel scoped+isolated persistent memory (owner-editable dashboard)
- ✅ admin governance (per-channel tool scope field, token budgets, audit log) · ✅ ambient (deterministic v1)
- ▲ connectors/tools at query-time + corpus ingestion/index = the next milestone (below)

## ✅ Corpus ingestion + indexing  ← the moat (LIVE — tested on real Lark, 210 docs/885 chunks)
> Read an org's EXISTING knowledge, index it, retrieve at query time.
> Claude Tag does NOT do this (connectors are query-time, no Lark connector). This is the wedge.

- [x] **Lark wiki crawler** (`ingest/crawler.py`) via `lark-cli`: wiki spaces → nodes (recurse on
      `has_child`) → docx `raw_content`. Rides the authorized user token (permission-faithful).
- [x] **Index:** chunk → **SQLite FTS5** (BM25) corpus, **workspace-scoped + fenced** (`corpus_*` store methods).
- [x] **Retrieval blend:** corpus_search fused into the orchestrator's system prompt at query time.
- [x] **CLI:** `agent-tag lark-spaces`, `agent-tag ingest --space <id>`; **Knowledge page** in the console.
- [ ] **Embeddings (upgrade from FTS5):** pluggable embedder (BYO key) → vector index for semantic recall.
- [ ] **Storage swap:** `PostgresStore` + pgvector for scale (in-memory/sqlite stay the defaults).
- [ ] **More sources:** Google Drive (`files.list`/`export`), Notion (search→blocks), Lark Sheets/Bitable readers.
- [ ] **Organize/normalize + re-sync:** dedupe, section extraction, freshness/`decay_at`, incremental refresh on doc-change.
- [ ] **Privacy:** per-source consent, right-to-erasure, private-source exclusion (hard gate).

## 🔜 Platform adapters (this build scaffolds; needs creds to live-test)
- [~] Lark adapter — WS long-conn (`open.larksuite.com`), proactive send, streaming cards, files
- [~] Slack adapter — Bolt Socket Mode (`app_mention`, `thread_ts`)
- [~] Discord adapter — discord.py (mentions, threads)

## 🔜 Backends
- [~] `claude` (Anthropic API, BYO key) — streaming
- [~] `cli` (local Claude Code / Codex via ACP) — **DEV/dogfood only**; subscription auth for a
      shared multi-user bot violates vendor ToS (Anthropic Consumer Terms §3.7, OpenAI single-user).
- [ ] `openai` (OpenAI API, BYO key)
- [ ] Real ACP transport (Agent Client Protocol) so any ACP agent plugs in

## 🔜 v1 (after the wedge validates)
- [ ] Tool use through an **MCP gateway**: per-channel scope check + credential injection + audit
- [ ] Token **metering → enforcement** (estimate-reserve-reconcile, per-channel + org budgets, kill-switch)
- [ ] **Ambient** (deterministic stalled-task nudge first; LLM relevance gate later, with real eval data)
- [ ] Shared **task object** + multiplayer handoff + task-resolution (coreference)
- [ ] Admin **console** + RBAC; cross-channel memory **grants**
- [ ] Memory-isolation **red-team** suite (namespace fence; honest about in-context exfil being DLP's job)

## 🔜 Project
- [ ] Decide durable **name** (working name "Agent Tag" is weak/confusable — see plan §13) + Susan legal read
- [ ] `docker-compose.yml` (Postgres + pgvector) for the ingestion milestone
- [ ] CI (ruff + pytest), CONTRIBUTING, adapter/backend SDK docs (the contribution flywheel)
