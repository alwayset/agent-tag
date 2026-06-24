"""Deterministic ambient scheduler: respects interval, fires, stays silent when empty."""

from agent_tag.adapters.base import Adapter
from agent_tag.backends.echo import EchoBackend
from agent_tag.core.ambient import AmbientEngine
from agent_tag.core.memory import MemoryService
from agent_tag.core.orchestrator import TurnOrchestrator
from agent_tag.core.redaction import Redactor
from agent_tag.core.router import Router
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.workspace.service import WorkspaceService


class FakeAdapter(Adapter):
    platform = "lark"

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def stream_inbound(self):
        if False:
            yield

    async def send(self, channel_id, text, *, thread_id=None):
        self.sent.append(text)
        return "m"


def _orch(store):
    ws = WorkspaceService(store)
    org = ws.create_org("O", org_id="o1")
    ws.create_workspace(org.id, "W", ws_id="w1")
    router = Router(ws, default_org_id=org.id, default_workspace_id="w1", default_backend="echo")
    return ws, TurnOrchestrator(
        router=router,
        memory=MemoryService(store),
        redactor=Redactor(enabled=False),
        backends={"echo": EchoBackend()},
        default_backend="echo",
    )


async def test_ambient_respects_interval_then_fires():
    store = InMemoryStore()
    ws, orch = _orch(store)
    ch, pol = ws.bind_channel("w1", "lark", "oc1", "eng")
    pol.ambient_enabled = True
    pol.redaction_enabled = False
    store.put_policy(pol)
    MemoryService(store).bind(pol.memory_namespace).write("alice asked about the deploy plan")

    fake = FakeAdapter()
    t = [1000.0]
    eng = AmbientEngine(store, orch, {"lark": fake}, now=lambda: t[0])

    assert await eng.tick() == 0  # first pass starts the clock
    assert fake.sent == []
    t[0] = 1000.0 + 25 * 3600  # past the 24h interval
    assert await eng.tick() == 1
    assert fake.sent and fake.sent[0].startswith("🔔")


async def test_ambient_silent_without_memory():
    store = InMemoryStore()
    ws, orch = _orch(store)
    ch, pol = ws.bind_channel("w1", "lark", "oc2", "ops")
    pol.ambient_enabled = True
    store.put_policy(pol)  # no memory written

    fake = FakeAdapter()
    t = [1000.0]
    eng = AmbientEngine(store, orch, {"lark": fake}, now=lambda: t[0])
    await eng.tick()
    t[0] = 1000.0 + 25 * 3600
    assert await eng.tick() == 0  # nothing to follow up on → silent
    assert fake.sent == []
