"""Application wiring: build the store, services, backends, and orchestrator.

`build_core` is shared by the console runner (`build_app`) and the `serve` runtime
(web UI + live adapters + ambient). It seeds a default org/workspace idempotently
and builds every backend whose credentials are present.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_tag.adapters.base import Adapter
from agent_tag.adapters.registry import build_adapter
from agent_tag.backends.base import BackendAdapter
from agent_tag.backends.registry import build_backend
from agent_tag.config import Config
from agent_tag.core.memory import MemoryService
from agent_tag.core.orchestrator import TurnOrchestrator
from agent_tag.core.redaction import Redactor
from agent_tag.core.router import Router
from agent_tag.settings import SettingsService
from agent_tag.store.base import Store
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.workspace.service import WorkspaceService


def build_backends(config: Config) -> dict[str, BackendAdapter]:
    """Echo is always present. API backends build only if their key is set; the
    local-CLI backend builds if its CLI command is configured. A missing optional
    SDK simply omits that backend (the registry raises ImportError)."""
    backends: dict[str, BackendAdapter] = {"echo": build_backend("echo", config)}
    candidates = []
    if config.anthropic_api_key:
        candidates.append("claude")
    if config.openai_api_key:
        candidates.append("openai")
    if config.cli_command:
        candidates.append("cli")
    for name in candidates:
        try:
            backends[name] = build_backend(name, config)
        except Exception:  # noqa: BLE001 - SDK missing or build error → backend unavailable
            pass
    return backends


@dataclass(slots=True)
class CoreBundle:
    config: Config
    store: Store
    settings: SettingsService
    workspace: WorkspaceService
    memory: MemoryService
    redactor: Redactor
    orchestrator: TurnOrchestrator
    backends: dict[str, BackendAdapter]
    org_id: str
    workspace_id: str


def build_core(config: Config, store: Store, settings: SettingsService | None = None) -> CoreBundle:
    settings = settings or SettingsService(store, config)
    workspace = WorkspaceService(store)

    orgs = store.list_orgs()
    if orgs:
        org = orgs[0]
        wss = store.list_workspaces(org.id)
        ws = wss[0] if wss else workspace.create_workspace(org.id, "Default Workspace")
    else:
        org = workspace.create_org("My Company", org_id="org_default")
        ws = workspace.create_workspace(org.id, "Default Workspace", ws_id="ws_default")

    memory = MemoryService(store)
    redactor = Redactor(enabled=config.redaction_enabled)
    backends = build_backends(config)

    default_backend = settings.get("default_backend") or config.backend or "echo"
    if default_backend not in backends:
        default_backend = "echo"

    router = Router(
        workspace,
        default_org_id=org.id,
        default_workspace_id=ws.id,
        default_backend=default_backend,
        default_model=config.model,
        auto_bind=True,
        require_mention=True,
    )
    orchestrator = TurnOrchestrator(
        router=router,
        memory=memory,
        redactor=redactor,
        backends=backends,
        default_backend="echo",
    )
    return CoreBundle(
        config, store, settings, workspace, memory, redactor, orchestrator, backends, org.id, ws.id
    )


# --- console runner (zero-cred demo / quick local chat) ---


@dataclass(slots=True)
class App:
    core: CoreBundle
    adapter: Adapter

    @property
    def orchestrator(self) -> TurnOrchestrator:
        return self.core.orchestrator

    async def run(self) -> None:
        try:
            async for event in self.adapter.stream_inbound():
                await self.orchestrator.handle(event, self.adapter)
        finally:
            await self.adapter.close()
            for backend in self.orchestrator.backends.values():
                await backend.close()


def build_app(config: Config, *, store: Store | None = None) -> App:
    """Console / ephemeral runner. Uses an in-memory store by default."""
    store = store or InMemoryStore()
    core = build_core(config, store)
    adapter = build_adapter(config.adapter, config)
    return App(core, adapter)
