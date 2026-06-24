"""Backend registry — lazy import so the core runs without optional agent SDKs."""

from __future__ import annotations

import importlib

from agent_tag.backends.base import BackendAdapter

_BACKENDS: dict[str, tuple[str, str]] = {
    "echo": ("agent_tag.backends.echo", "EchoBackend"),
    "claude": ("agent_tag.backends.claude_api", "ClaudeApiBackend"),
    "openai": ("agent_tag.backends.openai_api", "OpenAIBackend"),
    "cli": ("agent_tag.backends.cli_acp", "CliAcpBackend"),
}


def available() -> list[str]:
    return sorted(_BACKENDS)


def build_backend(name: str, config) -> BackendAdapter:
    if name not in _BACKENDS:
        raise ValueError(f"unknown backend '{name}'. available: {available()}")
    mod_name, cls_name = _BACKENDS[name]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        raise ImportError(
            f"backend '{name}' needs an optional dependency "
            f"(e.g. pip install 'agent-tag[anthropic]'). original error: {exc}"
        ) from exc
    return getattr(mod, cls_name)(config)
