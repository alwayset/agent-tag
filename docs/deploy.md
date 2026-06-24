# Deploy

Agent Tag is a single Python process (`agent-tag serve`) that runs the admin
console, the enabled chat adapters, and the ambient scheduler in one event
loop. Run it with Docker, as a supervised OS service, or directly.

## Supervised service (keep it running, survive reboots)

```bash
agent-tag service install      # launchd (macOS) or a systemd unit (Linux)
agent-tag service status       # show PID + log path
agent-tag service uninstall
```

`install` registers a keep-alive service that starts `agent-tag serve` at login
and restarts it if it crashes. It bakes the current `PATH` into the service so
backends like the local `codex` / `claude` CLI remain reachable; logs go to
`~/Library/Logs/agent-tag.log` (macOS). Flags `--host/--port/--db/--token` match
`serve`. On Linux it writes a `--user` systemd unit and prints the enable command.

## Docker (recommended)

```bash
cp .env.example .env      # compose reads this; defaults are fine to start
docker compose up -d      # build + run detached
```

- Admin console: <http://localhost:8765>
- SQLite database persists in the named volume `agent_tag_data` (mounted at
  `/data` inside the container) across restarts and rebuilds.
- The container runs as a non-root user and binds `0.0.0.0:8765`; the compose
  file maps it to `localhost:8765` on the host.

Apply connection changes (made in the console) by restarting:

```bash
docker compose restart
```

Tear down (keeps the volume / your data):

```bash
docker compose down
```

To also delete the database: `docker compose down -v`.

## Bare pip

Requires Python 3.11+.

```bash
pip install -e '.[all]'                 # web + all adapters + all backends
agent-tag serve                         # 127.0.0.1:8765
agent-tag serve --host 0.0.0.0 --port 8765 --db /var/lib/agent-tag/agent_tag.db
```

Run it under a process manager (systemd, supervisor, pm2) so it restarts on
crash and on boot. The CLI flags `--host / --port / --db / --token` override
the corresponding env vars.

## Environment variables

Connection **credentials** (Lark / Slack / Discord tokens, backend API keys,
which backend/model) are set in the **admin console UI** and stored in the
database — you do **not** need them in the environment. The env vars below are
**infra-level** settings read at process start.

| Var | Default | Purpose |
|-----|---------|---------|
| `AGENT_TAG_DB` | `agent_tag.db` (cwd) | Path to the SQLite database file. Docker sets `/data/agent_tag.db`. |
| `AGENT_TAG_WEB_HOST` | `127.0.0.1` | Admin console bind host. Use `0.0.0.0` to expose (Docker default via CMD). |
| `AGENT_TAG_WEB_PORT` | `8765` | Admin console port. |
| `AGENT_TAG_ADMIN_TOKEN` | _(unset)_ | If set, the admin console requires this token. **Set this whenever the console is reachable beyond localhost.** |

The `.env` file also accepts the connection vars (`LARK_APP_ID`,
`ANTHROPIC_API_KEY`, etc.) as a convenience for pre-seeding, but the console is
the source of truth and the recommended place to manage them.

## Set an admin token

By default the console has no auth and is meant to sit on `127.0.0.1`. If you
expose it (bind `0.0.0.0`, put it behind a reverse proxy, etc.), protect it:

```bash
# Docker: add to .env
AGENT_TAG_ADMIN_TOKEN=choose-a-long-random-string

# bare pip
agent-tag serve --token choose-a-long-random-string
# or: export AGENT_TAG_ADMIN_TOKEN=...
```

Generate a strong value with e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Always front a public deployment with HTTPS (a reverse proxy such as Caddy /
nginx / Traefik).

## Where the database lives

Everything stateful — UI settings (including connection creds), per-channel
memory, audit log, and token usage — is one SQLite file:

- **Docker:** `/data/agent_tag.db` inside the container, persisted in the
  `agent_tag_data` named volume.
- **Bare pip:** the path in `AGENT_TAG_DB` (default `./agent_tag.db` in the
  working directory; pass `--db` for an absolute path).

## Backups

The database is a single SQLite file, so a backup is a file copy. Do it while
the process is stopped, or use SQLite's online backup to get a consistent copy
of a running DB:

```bash
# Docker — consistent online snapshot from the named volume:
docker compose exec agent-tag \
  sh -c "sqlite3 /data/agent_tag.db \".backup '/data/backup-$(date +%F).db'\""
docker compose cp agent-tag:/data/backup-$(date +%F).db ./backup-$(date +%F).db

# bare pip — stop the process, then copy the file:
cp /var/lib/agent-tag/agent_tag.db ./agent_tag.backup.db
```

Restore by stopping the process and replacing the file at `AGENT_TAG_DB` (and
`agent_tag-wal` / `-shm` sidecar files if present), then start again.

## Lark adapter choice and the `lark-cli` dependency

Agent Tag has two Lark adapters (set via `AGENT_TAG_ADAPTER`, or the console's
**Enabled chat platforms** field). They have different host requirements:

- **`larkcli`** (the recommended smooth path) shells out to the official
  `lark-cli` binary and reads its OAuth auth from `~/.lark-cli/`. So the host
  running `agent-tag serve` **must have the `lark-cli` binary installed and an
  authorized `~/.lark-cli/`** (run `lark-cli auth login` once on that host — see
  [`docs/lark-setup.md`](lark-setup.md), Option A). The same applies to the
  wiki ingest (`agent-tag lark-spaces` / `agent-tag ingest`).
- **`lark`** (custom app, advanced) connects via the `lark-oapi` SDK using
  App ID / App Secret you set in the console — **no external binary or
  filesystem auth needed.**

For a **Docker / containerized deploy**, `larkcli` therefore requires either
installing `lark-cli` into the image and mounting an authorized `~/.lark-cli/`
into the container (e.g. as a volume / bind mount on the user's home), or
running `lark-cli auth login` from inside the container so the auth lands in
the container's home. If that's inconvenient, use **Option B (custom app /
`lark` adapter)** for containerized deploys — it needs only the credentials
stored in the database and no host binary.

> The `larkcli` adapter holds a single Lark event stream. Run only **one**
> `lark-cli` event consumer per auth — don't run a second `agent-tag serve` (or
> a separate `lark-cli` long-connection session) against the same `~/.lark-cli/`
> at the same time.

## Restart to apply connection changes

Connection changes made in the console (Lark/Slack/Discord creds, the active
backend) take effect on the **next `serve` start** — v1 re-binds adapters only
at startup, and the console shows a reminder. After editing **Connections**:

- **Docker:** `docker compose restart`
- **bare pip:** stop and re-run `agent-tag serve` (or restart the systemd unit).

Workspace/channel bindings and memory are read live and do **not** require a
restart.
