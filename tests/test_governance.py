"""Per-channel token budget kill-switch."""

from agent_tag.adapters.base import Adapter, InboundEvent
from agent_tag.backends.echo import EchoBackend
from agent_tag.core.memory import MemoryService
from agent_tag.core.orchestrator import TurnOrchestrator
from agent_tag.core.redaction import Redactor
from agent_tag.core.router import Router
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.workspace.service import WorkspaceService


class FakeAdapter(Adapter):
    platform = "console"

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def stream_inbound(self):
        if False:
            yield

    async def send(self, channel_id, text, *, thread_id=None):
        self.sent.append(text)
        return "m"


def _build(budget):
    store = InMemoryStore()
    ws = WorkspaceService(store)
    org = ws.create_org("O", org_id="o1")
    wsp = ws.create_workspace(org.id, "W", ws_id="w1")
    ch, pol = ws.bind_channel(wsp.id, "console", "eng", "eng")
    pol.token_budget = budget
    store.put_policy(pol)
    router = Router(
        ws,
        default_org_id=org.id,
        default_workspace_id=wsp.id,
        default_backend="echo",
        auto_bind=True,
        require_mention=True,
    )
    orch = TurnOrchestrator(
        router=router,
        memory=MemoryService(store),
        redactor=Redactor(enabled=False),
        backends={"echo": EchoBackend()},
        default_backend="echo",
    )
    return store, orch, ch


def _ev(mid="1"):
    return InboundEvent(
        platform="console",
        channel_id="eng",
        user_id="alice",
        user_display_name="alice",
        text="hi @bot",
        mentions_bot=True,
        message_id=mid,
    )


async def test_budget_blocks_when_exceeded():
    store, orch, ch = _build(budget=10)
    store.add_usage(ch.id, 8, 5)  # total 13 >= 10
    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1 and "budget" in fake.sent[0].lower()
    assert any(e.action == "denied" for e in store.list_audit(ch.id))


async def test_no_budget_allows():
    store, orch, ch = _build(budget=None)
    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1 and "budget" not in fake.sent[0].lower()
