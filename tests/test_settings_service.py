"""SettingsService — env→DB seeding, secret masking, blank-secret skip, and the
full effective_config() mapping (DB layered over env defaults)."""

from __future__ import annotations

from agent_tag.config import Config
from agent_tag.settings import SettingsService
from agent_tag.store.memory_store import InMemoryStore


def test_seed_only_fills_missing_keys():
    store = InMemoryStore()
    store.set_setting("lark_app_id", "preexisting")  # already in DB
    s = SettingsService(store, Config(lark_app_id="from_env", anthropic_api_key="sk-env"))
    # existing DB value is NOT overwritten by the env seed
    assert s.get("lark_app_id") == "preexisting"
    # a key absent from the DB IS seeded from env
    assert s.get("anthropic_api_key") == "sk-env"


def test_seed_skips_empty_env_defaults():
    s = SettingsService(InMemoryStore(), Config())  # nothing set
    # no env value → key stays unset in the store (falls back to env default, which is None)
    assert s.store.get_setting("lark_app_secret") is None
    assert s.get("lark_app_secret") is None


def test_default_backend_env_mapping_promotes_echo_to_claude():
    # _env_default maps the env "echo" default to "claude" for new channels.
    s = SettingsService(InMemoryStore(), Config(backend="echo"))
    assert s.get("default_backend") == "claude"
    s2 = SettingsService(InMemoryStore(), Config(backend="openai"))
    assert s2.get("default_backend") == "openai"


def test_enabled_adapters_env_default_falls_back_to_lark():
    s = SettingsService(InMemoryStore(), Config(adapter="console"))
    # console is not a chat platform → enabled_adapters env default is lark
    assert s.enabled_adapters() == ["lark"]


def test_masked_secret_vs_plain():
    s = SettingsService(InMemoryStore(), Config(anthropic_api_key="sk-secret", lark_app_id="cli_x"))
    assert s.masked("anthropic_api_key") == "••••••••"
    assert s.masked("lark_app_id") == "cli_x"
    # unset secret masks to empty, not bullets
    assert s.masked("openai_api_key") == ""


def test_update_many_skips_blank_secret_but_writes_blank_plain():
    s = SettingsService(InMemoryStore(), Config(anthropic_api_key="sk-keep", lark_app_id="cli_old"))
    s.update_many(
        {
            "anthropic_api_key": "",  # blank secret = "unchanged" from the UI → keep
            "openai_api_key": "sk-new",  # non-blank secret → write
            "lark_app_id": "",  # blank non-secret → actually written (cleared)
        }
    )
    assert s.get("anthropic_api_key") == "sk-keep"
    assert s.get("openai_api_key") == "sk-new"
    assert s.get("lark_app_id") == ""


def test_is_configured_checks_a_group_prefix():
    # The OpenAI backend group has no defaulted setting, so it starts unconfigured.
    s = SettingsService(InMemoryStore(), Config())
    assert s.is_configured("Backend — OpenAI") is False
    s.set("openai_api_key", "sk-o")
    assert s.is_configured("Backend — OpenAI") is True


def test_effective_config_full_mapping():
    s = SettingsService(InMemoryStore(), Config())
    s.update_many(
        {
            "default_backend": "openai",
            "default_model": "gpt-x",
            "anthropic_api_key": "sk-a",
            "openai_api_key": "sk-o",
            "cli_command": "codex",
            "lark_app_id": "cli_app",
            "lark_app_secret": "shh",
            "lark_domain": "https://open.feishu.cn",
            "enabled_adapters": "slack,discord",
        }
    )
    cfg = s.effective_config()
    assert cfg.backend == "openai"
    assert cfg.model == "gpt-x"
    assert cfg.anthropic_api_key == "sk-a"
    assert cfg.openai_api_key == "sk-o"
    assert cfg.cli_command == "codex"
    assert cfg.lark_app_id == "cli_app"
    assert cfg.lark_app_secret == "shh"
    assert cfg.lark_domain == "https://open.feishu.cn"
    # effective_config picks the FIRST adapter for the single-adapter Config.adapter
    assert cfg.adapter == "slack"
    # ...while enabled_adapters() returns the whole list
    assert s.enabled_adapters() == ["slack", "discord"]


def test_effective_config_defaults_when_unset():
    cfg = SettingsService(InMemoryStore(), Config()).effective_config()
    assert cfg.backend == "claude"  # env-default promotion
    assert cfg.adapter == "lark"
    assert cfg.lark_domain == "https://open.larksuite.com"
    assert cfg.cli_command == "claude"
