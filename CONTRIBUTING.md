# Contributing to Agent Tag

Thanks for your interest in Agent Tag — an open, self-hosted, agent-agnostic AI
teammate for group chat (Lark / Slack / Discord). This guide covers local
development, the project layout, and how to extend the two main seams: chat
**adapters** and agent **backends**.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Dev setup

Requires **Python 3.11+**.

```bash
git clone https://github.com/alwayset/agent-tag.git
cd agent-tag

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install -e '.[all]'              # web console + all adapters + all LLM backends
pip install -e '.[dev]'              # pytest, pytest-asyncio, ruff
```

The core depends only on the standard library — adapters and backends pull their
own extras (`lark`, `slack`, `discord`, `anthropic`, `openai`, `web`, `all`). For
day-to-day development, `'.[all]'` plus `'.[dev]'` is the simplest setup.

Smoke-test the install with the zero-credential demo (no accounts, no keys):

```bash
agent-tag run --adapter console --backend echo
```

## Running tests

The suite uses **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`, so
`async def test_*` functions run without a per-test decorator).

```bash
pytest                  # full suite (24 passing)
pytest tests/test_memory_isolation.py   # one file
pytest -k redaction     # by keyword
```

Tests live in `tests/` and cover the load-bearing invariants: memory isolation,
governance/budgets, redaction/DLP, the orchestrator, the ambient engine, corpus
ingestion, settings, and the SQLite store. **Any change to those areas needs test
coverage**, and the existing tests must stay green.

## Lint and format

We use **ruff** for both linting and formatting (line length 100, target
`py311`).

```bash
ruff check .            # lint
ruff check --fix .      # lint + autofix
ruff format .           # format
```

Run `ruff check` and `ruff format` before opening a PR; CI enforces a clean tree.

## Project layout

```
agent_tag/
  adapters/      chat platforms → normalized InboundEvent + send  (console, larkcli, lark, slack, discord)
  backends/      the agent harness seam (echo, claude, openai, cli)
  core/          router, channel policy, orchestrator, memory, redaction/DLP, ambient engine
  store/         SQLite store (settings, memory, audit) + FTS5 corpus
  ingest/        Lark wiki crawler + indexer (corpus → SQLite FTS5)
  web/           FastAPI admin console (templates + static)
  workspace/     Organization → Workspace → Channel model
  app.py         wires adapter + backend + core for `run`
  serve.py       runs web console + adapters + ambient concurrently
  cli.py         console-script entrypoint (agent-tag ...)
tests/           pytest suite
docs/            lark-setup.md, deploy.md
site/            landing page (GitHub Pages)
```

Two interfaces are the extension surface and should stay stable:

- **`Adapter`** (`agent_tag/adapters/base.py`) — one chat platform → a normalized
  `InboundEvent` stream + `send`.
- **`BackendAdapter`** (`agent_tag/backends/base.py`) — rent a harness (Claude /
  OpenAI / local CLI / any ACP agent) behind one seam, streaming `Delta`s back.

## Adding a chat adapter

An adapter normalizes a chat platform into the common contract; nothing else in
the system changes.

1. Create `agent_tag/adapters/<name>.py` with a class that subclasses
   `agent_tag.adapters.base.Adapter`:
   - set the `platform` class attribute (e.g. `"telegram"`),
   - implement `stream_inbound()` as an `async def` generator yielding
     `InboundEvent(...)`,
   - implement `async def send(self, channel_id, text, *, thread_id=None)`.
   - Optionally override `edit`, `fetch_history`, `fetch_file`, and `close`.
2. Register it in `agent_tag/adapters/registry.py` by adding an entry to the
   `_ADAPTERS` map: `"<name>": ("agent_tag.adapters.<name>", "<ClassName>")`.
   The registry imports lazily, so a missing SDK only errors when that adapter is
   selected.
3. If the adapter needs a third-party SDK, add an optional-dependency extra in
   `pyproject.toml` (mirroring `lark` / `slack` / `discord`) so it installs via
   `pip install 'agent-tag[<name>]'`.
4. Add a test under `tests/` (the `console` adapter is the simplest reference).

## Adding an agent backend

A backend is the LLM harness Agent Tag rents to produce a reply. Agent Tag does
**not** implement its own agent loop — it stays model-agnostic behind this seam.

1. Create `agent_tag/backends/<name>.py` with a class that subclasses
   `agent_tag.backends.base.BackendAdapter`:
   - set the `name` class attribute,
   - implement `run_turn(self, req: TurnRequest)` as an `async def` generator
     streaming `Delta(type="text", ...)` then `Delta(type="done")`,
   - optionally override `report_usage()` (for token metering / budgets) and
     `close()`.
2. Register it in `agent_tag/backends/registry.py` by adding an entry to the
   `_BACKENDS` map: `"<name>": ("agent_tag.backends.<name>", "<ClassName>")`.
3. Add the SDK as an optional-dependency extra in `pyproject.toml` if needed.
4. Add a test. `EchoBackend` (`agent_tag/backends/echo.py`) is the no-LLM
   reference — it proves the full pipeline without spending a token.

## Commit and PR conventions

- Keep commits focused and the subject line in the **imperative mood**
  (e.g. "Add Telegram adapter", not "Added" / "Adds").
- Branch off `main`; open a pull request against `main`.
- A PR should: pass `pytest`, be clean under `ruff check` and `ruff format`, and
  update docs when behavior changes. The
  [pull request template](.github/PULL_REQUEST_TEMPLATE.md) has the checklist.
- Keep PRs small and reviewable; describe what changed and why.

## Developer Certificate of Origin (DCO)

Contributions are accepted under the project's [Apache-2.0](LICENSE) license. We
require a **DCO sign-off** on every commit to certify you have the right to submit
the work (see <https://developercertificate.org>). Add the `Signed-off-by` trailer
by committing with `-s`:

```bash
git commit -s -m "Add Telegram adapter"
```

This appends a line like:

```
Signed-off-by: Your Name <you@example.com>
```

Use a real name and email. Commits without a sign-off will be asked to amend.
