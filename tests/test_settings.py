"""SettingsService: env seed, DB override, masking, effective config."""

from agent_tag.config import Config
from agent_tag.settings import SettingsService
from agent_tag.store.memory_store import InMemoryStore


def test_seed_from_env_and_override():
    env = Config(lark_app_id="cli_env", anthropic_api_key="sk-env")
    s = SettingsService(InMemoryStore(), env)
    assert s.get("lark_app_id") == "cli_env"  # seeded from env
    s.set("lark_app_id", "cli_ui")  # UI override
    assert s.get("lark_app_id") == "cli_ui"


def test_masks_secrets_but_not_plain():
    env = Config(anthropic_api_key="sk-secret", lark_app_id="cli_123")
    s = SettingsService(InMemoryStore(), env)
    assert s.masked("anthropic_api_key") == "••••••••"
    assert s.masked("lark_app_id") == "cli_123"


def test_update_many_ignores_blank_secret():
    env = Config(anthropic_api_key="sk-keep")
    s = SettingsService(InMemoryStore(), env)
    s.update_many({"anthropic_api_key": "", "lark_app_id": "cli_new"})
    assert s.get("anthropic_api_key") == "sk-keep"  # blank secret submit is ignored
    assert s.get("lark_app_id") == "cli_new"


def test_effective_config_builds_from_settings():
    s = SettingsService(InMemoryStore(), Config())
    s.set("default_backend", "claude")
    s.set("anthropic_api_key", "sk-x")
    s.set("enabled_adapters", "lark,slack")
    cfg = s.effective_config()
    assert cfg.backend == "claude" and cfg.anthropic_api_key == "sk-x"
    assert s.enabled_adapters() == ["lark", "slack"]
