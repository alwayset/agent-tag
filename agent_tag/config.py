"""Configuration, loaded from environment / a .env file.

Billing model: BYO metered API key. Agent Tag ships NO billing code and does
NOT reuse subscription/coding-plan tokens — doing so for a shared multi-user
bot is prohibited by both Anthropic (Consumer Terms §3.7) and OpenAI. See
TODO.md / the plan for detail.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


@dataclass(slots=True)
class Config:
    # Which IM adapter + agent backend to run
    adapter: str = "console"
    backend: str = "echo"
    model: str | None = None

    # Backend creds (BYO-API-key)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # Local-CLI dogfood backend (subscription auth — DEV ONLY, see warning in cli_acp)
    cli_command: str = "claude"          # or "codex"

    # Platform creds
    lark_app_id: str | None = None
    lark_app_secret: str | None = None
    lark_domain: str = "https://open.larksuite.com"   # international; Feishu = open.feishu.cn
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    discord_token: str | None = None

    # Behavior
    redaction_enabled: bool = True

    # Infra (env-only; not UI-edited)
    db_path: str = "agent_tag.db"
    web_host: str = "127.0.0.1"
    web_port: int = 8765
    admin_token: str | None = None       # if set, the admin UI requires this token
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, *, load_dotenv: bool = True) -> "Config":
        if load_dotenv:
            _load_dotenv()
        g = os.environ.get
        return cls(
            adapter=g("AGENT_TAG_ADAPTER", "console"),
            backend=g("AGENT_TAG_BACKEND", "echo"),
            model=g("AGENT_TAG_MODEL") or None,
            anthropic_api_key=g("ANTHROPIC_API_KEY"),
            openai_api_key=g("OPENAI_API_KEY"),
            cli_command=g("AGENT_TAG_CLI_COMMAND", "claude"),
            lark_app_id=g("LARK_APP_ID"),
            lark_app_secret=g("LARK_APP_SECRET"),
            lark_domain=g("LARK_DOMAIN", "https://open.larksuite.com"),
            slack_bot_token=g("SLACK_BOT_TOKEN"),
            slack_app_token=g("SLACK_APP_TOKEN"),
            discord_token=g("DISCORD_TOKEN"),
            redaction_enabled=g("AGENT_TAG_REDACTION", "1") not in ("0", "false", "False"),
            db_path=g("AGENT_TAG_DB", "agent_tag.db"),
            web_host=g("AGENT_TAG_WEB_HOST", "127.0.0.1"),
            web_port=int(g("AGENT_TAG_WEB_PORT", "8765")),
            admin_token=g("AGENT_TAG_ADMIN_TOKEN") or None,
        )
