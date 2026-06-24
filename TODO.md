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

## 🔜 Corpus ingestion + indexing  ← the moat (deferred per Eric, the big TODO)
> Read an org's EXISTING knowledge, organize it, and index it for retrieval.
> Claude Tag does NOT do this (connectors are query-time, no Lark connector).
> This is where Agent Tag wins. Land it as its own milestone.

- [ ] **Storage swap:** add `PostgresStore` (Store impl) with **pgvector** for embeddings
      (the in-memory store stays the default for `console`/tests).
- [ ] **Embedding layer:** pluggable embedder (BYO key) → chunk → vector index, keyed by namespace.
- [ ] **Lark corpus crawler** (`ingestion/lark.py`):
      - Wiki: `GET /open-apis/wiki/v2/spaces` → `…/spaces/{id}/nodes` (recurse on `has_child`)
        → resolve `obj_token`/`obj_type` → `docx` `raw_content`/blocks.
      - Drive: `GET /open-apis/drive/v1/files` folder walk (recurse).
      - Sheets / Bitable: separate readers.
      - Auth: `user_access_token` for a permission-faithful crawl; `im:message.group_msg`
        (full history) is sensitive + platform-reviewed → gate behind review + retention policy.
      - Rate limits ~5 req/s/chat — backoff + paging.
- [ ] **Google Drive crawler** (`ingestion/gdrive.py`): `files.list` walk + `files.export`.
- [ ] **Notion crawler** (`ingestion/notion.py`): search → blocks.
- [ ] **Organize/normalize pass:** dedupe, title/section extraction, freshness/`decay_at`,
      provenance (so retrieved corpus is attributable + can be re-synced on change).
- [ ] **Re-sync:** incremental refresh on doc-change events (Lark drive subscription / Drive push).
- [ ] **Retrieval blend:** fuse corpus index + distilled interaction memory at query time.
- [ ] **Privacy:** per-source consent, right-to-erasure on distilled memory, private-source exclusion (hard gate).

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
