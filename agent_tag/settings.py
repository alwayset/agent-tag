"""SettingsService — UI-editable configuration, persisted in the store.

Effective config = DB settings (edited in the admin UI) layered over environment
defaults (12-factor / headless deploys). On first run the DB is seeded from env so
either workflow works. The web UI reads `SETTING_SPECS` to render the Connections
page generically and masks secrets.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_tag.config import Config
from agent_tag.store.base import Store


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    group: str
    secret: bool = False
    help: str = ""
    placeholder: str = ""


SETTING_SPECS: list[SettingSpec] = [
    # Lark
    SettingSpec(
        "lark_app_id",
        "Lark App ID",
        "Lark",
        help="From the Lark Developer Console.",
        placeholder="cli_xxx",
    ),
    SettingSpec("lark_app_secret", "Lark App Secret", "Lark", secret=True),
    SettingSpec(
        "lark_domain",
        "Lark Domain",
        "Lark",
        help="International: https://open.larksuite.com · Feishu: https://open.feishu.cn",
        placeholder="https://open.larksuite.com",
    ),
    # Backends
    SettingSpec(
        "anthropic_api_key",
        "Anthropic API Key",
        "Backend — Claude (API)",
        secret=True,
        help="BYO key — the compliant path for a shared/hosted bot.",
        placeholder="sk-ant-...",
    ),
    SettingSpec(
        "openai_api_key",
        "OpenAI API Key",
        "Backend — OpenAI (API)",
        secret=True,
        placeholder="sk-...",
    ),
    SettingSpec(
        "cli_command",
        "Coding-agent CLI command",
        "Backend — Coding plan (local CLI)",
        help="'claude' (Claude Code) or 'codex'. Uses YOUR local plan; self-host only.",
        placeholder="claude",
    ),
    SettingSpec(
        "default_model", "Default model id", "Backend — defaults", placeholder="claude-opus-4-8"
    ),
    SettingSpec(
        "default_backend",
        "Default backend for new channels",
        "Backend — defaults",
        help="echo | claude | openai | cli",
        placeholder="claude",
    ),
    # Slack / Discord (optional)
    SettingSpec("slack_bot_token", "Slack Bot Token", "Slack", secret=True, placeholder="xoxb-..."),
    SettingSpec("slack_app_token", "Slack App Token", "Slack", secret=True, placeholder="xapp-..."),
    SettingSpec("discord_token", "Discord Bot Token", "Discord", secret=True),
    # Runtime
    SettingSpec(
        "enabled_adapters",
        "Enabled chat platforms",
        "Runtime",
        help="Comma-separated: lark, slack, discord",
        placeholder="lark",
    ),
]

_SECRET_KEYS = {s.key for s in SETTING_SPECS if s.secret}


class SettingsService:
    def __init__(self, store: Store, env: Config | None = None) -> None:
        self.store = store
        self.env = env or Config.from_env()
        self._seed_from_env()

    def _env_default(self, key: str) -> str | None:
        # map setting key -> env Config attribute (same names, plus a couple of extras)
        if key == "enabled_adapters":
            return self.env.adapter if self.env.adapter in ("lark", "slack", "discord") else "lark"
        if key == "default_backend":
            return self.env.backend if self.env.backend != "echo" else "claude"
        if key == "default_model":
            return self.env.model
        val = getattr(self.env, key, None)
        if isinstance(val, bool):
            return "1" if val else "0"
        return val

    def _seed_from_env(self) -> None:
        for spec in SETTING_SPECS:
            if self.store.get_setting(spec.key) is None:
                default = self._env_default(spec.key)
                if default:
                    self.store.set_setting(spec.key, str(default))

    def get(self, key: str) -> str | None:
        v = self.store.get_setting(key)
        return v if v is not None else self._env_default(key)

    def set(self, key: str, value: str) -> None:
        self.store.set_setting(key, value)

    def update_many(self, values: dict[str, str]) -> None:
        for k, v in values.items():
            # don't overwrite a secret with an empty submit (UI sends blank for unchanged)
            if k in _SECRET_KEYS and v == "":
                continue
            self.store.set_setting(k, v)

    def is_configured(self, group_prefix: str) -> bool:
        """True if at least one non-empty setting exists for a group (for the UI checklist)."""
        for s in SETTING_SPECS:
            if s.group.startswith(group_prefix) and (self.get(s.key) or "").strip():
                return True
        return False

    def effective_config(self) -> Config:
        g = self.get
        return Config(
            adapter=(g("enabled_adapters") or "lark").split(",")[0].strip() or "lark",
            backend=g("default_backend") or "claude",
            model=g("default_model") or None,
            anthropic_api_key=g("anthropic_api_key"),
            openai_api_key=g("openai_api_key"),
            cli_command=g("cli_command") or "claude",
            lark_app_id=g("lark_app_id"),
            lark_app_secret=g("lark_app_secret"),
            lark_domain=g("lark_domain") or "https://open.larksuite.com",
            slack_bot_token=g("slack_bot_token"),
            slack_app_token=g("slack_app_token"),
            discord_token=g("discord_token"),
            redaction_enabled=(g("redaction_enabled") or "1") not in ("0", "false", "False"),
        )

    def enabled_adapters(self) -> list[str]:
        raw = self.get("enabled_adapters") or "lark"
        return [a.strip() for a in raw.split(",") if a.strip()]

    def masked(self, key: str) -> str:
        """Value for display: secrets shown as a fixed mask if set."""
        val = self.get(key) or ""
        if key in _SECRET_KEYS and val:
            return "••••••••"
        return val
