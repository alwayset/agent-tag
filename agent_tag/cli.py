"""Command-line entrypoint.

  agent-tag serve                 # run the admin web UI + chat adapters + ambient
  agent-tag run --adapter console --backend echo   # quick local chat (zero creds)
"""
from __future__ import annotations

import argparse
import asyncio

from agent_tag.adapters.registry import available as adapters_available
from agent_tag.backends.registry import available as backends_available
from agent_tag.config import Config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-tag", description="Agent Tag — open IM teammate")
    sub = parser.add_subparsers(dest="cmd")

    serve_p = sub.add_parser("serve", help="run the admin console + chat adapters + ambient")
    serve_p.add_argument("--host", help="web host (default 127.0.0.1)")
    serve_p.add_argument("--port", type=int, help="web port (default 8765)")
    serve_p.add_argument("--db", help="sqlite db path (default agent_tag.db)")
    serve_p.add_argument("--token", help="require this admin token to access the console")

    run_p = sub.add_parser("run", help="quick local chat (console)")
    run_p.add_argument("--adapter", help=f"IM adapter {adapters_available()}")
    run_p.add_argument("--backend", help=f"agent backend {backends_available()}")
    run_p.add_argument("--model", help="model id for the backend")

    args = parser.parse_args(argv)
    config = Config.from_env()

    if args.cmd == "serve":
        if args.host:
            config.web_host = args.host
        if args.port:
            config.web_port = args.port
        if args.db:
            config.db_path = args.db
        if args.token:
            config.admin_token = args.token
        from agent_tag.serve import serve
        try:
            asyncio.run(serve(config))
        except KeyboardInterrupt:
            print("\n[agent-tag] bye")
        return 0

    # default: console run
    if getattr(args, "adapter", None):
        config.adapter = args.adapter
    if getattr(args, "backend", None):
        config.backend = args.backend
    if getattr(args, "model", None):
        config.model = args.model

    from agent_tag.app import build_app
    app = build_app(config)
    print(f"[agent-tag] adapter={config.adapter} backend={config.backend}"
          f"  (adapters={adapters_available()} backends={backends_available()})")
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n[agent-tag] bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
