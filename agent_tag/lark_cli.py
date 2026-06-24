"""Thin wrapper around the `lark-cli` binary.

Agent Tag rides Lark CLI for Lark access (events, sending, and the corpus crawl)
so the operator authorizes once via Lark CLI's click-a-link OAuth instead of hand-
configuring app scopes. Both the Lark adapter and the ingestion crawler use this.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess


def find_lark_cli(config=None) -> str | None:
    """Locate the lark-cli binary: explicit setting → $LARK_CLI_PATH → PATH → nvm."""
    if config is not None:
        cand = (getattr(config, "extra", {}) or {}).get("lark_cli_path")
        if cand:
            return cand
    env = os.environ.get("LARK_CLI_PATH")
    if env:
        return env
    found = shutil.which("lark-cli")
    if found:
        return found
    for p in sorted(
        glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/lark-cli")), reverse=True
    ):
        if os.path.exists(p):
            return p
    return None


class LarkCliError(RuntimeError):
    pass


class LarkCli:
    def __init__(self, binary: str | None = None, config=None) -> None:
        self.binary = binary or find_lark_cli(config)

    def available(self) -> bool:
        return bool(
            self.binary
            and os.path.exists(self.binary)
            or (self.binary and shutil.which(self.binary))
        )

    def whoami(self) -> dict | None:
        """Best-effort: read ~/.lark-cli/config.json to report the authed user."""
        try:
            cfg = json.loads(open(os.path.expanduser("~/.lark-cli/config.json")).read())
            apps = cfg.get("apps", [])
            if apps:
                users = apps[0].get("users", [])
                return {
                    "app_id": apps[0].get("appId"),
                    "brand": apps[0].get("brand"),
                    "user": users[0].get("userName") if users else None,
                }
        except Exception:  # noqa: BLE001
            return None
        return None

    def api(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        as_: str = "user",
        timeout: int = 120,
    ) -> dict:
        if not self.binary:
            raise LarkCliError("lark-cli not found (install it / set LARK_CLI_PATH)")
        args = [self.binary, "api", method, path, "--as", as_, "--format", "json"]
        if params:
            args += ["--params", json.dumps(params)]
        if data:
            args += ["--data", json.dumps(data)]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise LarkCliError((proc.stderr or proc.stdout).strip()[:500])
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LarkCliError(f"bad JSON from lark-cli: {exc}; out={proc.stdout[:200]}") from exc
        if isinstance(payload, dict) and payload.get("code") not in (0, None):
            raise LarkCliError(f"lark api code={payload.get('code')} msg={payload.get('msg')}")
        return payload

    def paged(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        as_: str = "user",
        item_key: str = "items",
        max_pages: int = 50,
    ) -> list[dict]:
        """Iterate a paginated Lark list endpoint, returning all items."""
        params = dict(params or {})
        out: list[dict] = []
        for _ in range(max_pages):
            payload = self.api(method, path, params=params, as_=as_)
            data = payload.get("data", {}) or {}
            out.extend(data.get(item_key, []) or [])
            if not data.get("has_more"):
                break
            token = data.get("page_token")
            if not token:
                break
            params["page_token"] = token
        return out
