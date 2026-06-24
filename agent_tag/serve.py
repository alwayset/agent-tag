"""`agent-tag serve` — the production runtime.

Runs three things in one event loop:
  1. the admin web UI (FastAPI/uvicorn) — always on, so you can configure from a browser
  2. the enabled chat adapters (Lark / Slack / Discord) — started if their creds are set
  3. the ambient scheduler

Connection changes made in the UI take effect on the next `serve` start (v1: restart
to re-bind adapters; the UI shows a reminder).
"""
from __future__ import annotations

import asyncio

from agent_tag.adapters.registry import build_adapter
from agent_tag.app import build_core
from agent_tag.config import Config
from agent_tag.core.ambient import AmbientEngine
from agent_tag.settings import SettingsService
from agent_tag.store.sqlite_store import SqliteStore


def _adapter_ready(name: str, cfg: Config) -> bool:
    if name == "larkcli":                       # smooth path: just needs lark-cli authed
        from agent_tag.lark_cli import find_lark_cli
        return bool(find_lark_cli(cfg))
    if name == "lark":                          # custom-app path: needs app creds
        return bool(cfg.lark_app_id and cfg.lark_app_secret)
    if name == "slack":
        return bool(cfg.slack_bot_token and cfg.slack_app_token)
    if name == "discord":
        return bool(cfg.discord_token)
    return False


async def _drain(adapter, orchestrator) -> None:
    try:
        async for event in adapter.stream_inbound():
            await orchestrator.handle(event, adapter)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[agent-tag] adapter '{getattr(adapter, 'platform', '?')}' stopped: {exc}")


async def serve(env_config: Config) -> None:
    store = SqliteStore(env_config.db_path)
    settings = SettingsService(store, env_config)

    # Effective config = UI/DB settings, with infra fields carried from env.
    cfg = settings.effective_config()
    cfg.db_path = env_config.db_path
    cfg.web_host = env_config.web_host
    cfg.web_port = env_config.web_port
    cfg.admin_token = env_config.admin_token

    core = build_core(cfg, store, settings)

    # Start configured adapters.
    senders: dict = {}
    drain_tasks: list[asyncio.Task] = []
    for name in settings.enabled_adapters():
        if not _adapter_ready(name, cfg):
            print(f"[agent-tag] adapter '{name}' enabled but not configured — skipping "
                  f"(set its credentials in the console, then restart).")
            continue
        try:
            adapter = build_adapter(name, cfg)
        except Exception as exc:  # noqa: BLE001 - missing SDK etc.
            print(f"[agent-tag] could not start adapter '{name}': {exc}")
            continue
        senders[adapter.platform] = adapter
        drain_tasks.append(asyncio.create_task(_drain(adapter, core.orchestrator)))
        print(f"[agent-tag] adapter '{name}' running")

    stop = asyncio.Event()
    ambient = AmbientEngine(store, core.orchestrator, senders)
    ambient_task = asyncio.create_task(ambient.run(stop))

    # Web UI.
    from agent_tag.web import create_app  # imported here so core runs without web extras
    import uvicorn

    app = create_app(core, settings, cfg)
    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.web_host, port=cfg.web_port, log_level="warning", loop="asyncio"))

    url = f"http://{cfg.web_host}:{cfg.web_port}"
    print(f"\n  Agent Tag is running.\n  → Admin console:  {url}\n"
          f"  → Chat adapters:  {', '.join(senders) or '(none configured yet — set them in the console)'}\n")
    try:
        await server.serve()
    finally:
        stop.set()
        for t in (*drain_tasks, ambient_task):
            t.cancel()
        for a in senders.values():
            try:
                await a.close()
            except Exception:  # noqa: BLE001
                pass
        for b in core.backends.values():
            try:
                await b.close()
            except Exception:  # noqa: BLE001
                pass
