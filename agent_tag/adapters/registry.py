"""Adapter registry — lazy import so the core runs without optional platform SDKs.

Only the adapter you select needs its extra installed
(e.g. `pip install 'agent-tag[lark]'`).
"""
from __future__ import annotations

import importlib

from agent_tag.adapters.base import Adapter

_ADAPTERS: dict[str, tuple[str, str]] = {
    "console": ("agent_tag.adapters.console", "ConsoleAdapter"),
    "larkcli": ("agent_tag.adapters.larkcli", "LarkCliAdapter"),  # smooth path (rides lark-cli)
    "lark": ("agent_tag.adapters.lark", "LarkAdapter"),           # custom-app path (lark-oapi SDK)
    "slack": ("agent_tag.adapters.slack", "SlackAdapter"),
    "discord": ("agent_tag.adapters.discord", "DiscordAdapter"),
}


def available() -> list[str]:
    return sorted(_ADAPTERS)


def build_adapter(name: str, config) -> Adapter:
    if name not in _ADAPTERS:
        raise ValueError(f"unknown adapter '{name}'. available: {available()}")
    mod_name, cls_name = _ADAPTERS[name]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:  # missing optional SDK
        raise ImportError(
            f"adapter '{name}' needs an optional dependency. "
            f"Try: pip install 'agent-tag[{name}]'  (original error: {exc})"
        ) from exc
    return getattr(mod, cls_name)(config)
