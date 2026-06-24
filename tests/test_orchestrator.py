"""End-to-end: multiple users share one teammate per channel, memory accumulates
per channel and stays isolated, and message ids are idempotent."""
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
        self.sent: list[tuple[str, str]] = []

    async def stream_inbound(self):  # not used; we call handle() directly
        if False:
            yield  # pragma: no cover

    async def send(self, channel_id, text, *, thread_id=None):
        self.sent.append((channel_id, text))
        return "m1"


def _build():
    store = InMemoryStore()
    ws = WorkspaceService(store)
    org = ws.create_org("Org", org_id="org1")
    wsp = ws.create_workspace(org.id, "WS", ws_id="ws1")
    router = Router(
        ws, default_org_id=org.id, default_workspace_id=wsp.id,
        default_backend="echo", auto_bind=True, require_mention=True,
    )
    orch = TurnOrchestrator(
        router=router, memory=MemoryService(store), redactor=Redactor(enabled=True),
        backends={"echo": EchoBackend()}, default_backend="echo",
    )
    return store, orch


def _ev(user, channel, text, mid):
    return InboundEvent(
        platform="console", channel_id=channel, user_id=user, user_display_name=user,
        text=text, mentions_bot=True, message_id=mid,
    )


async def test_multiuser_shared_channel_and_isolation():
    store, orch = _build()
    fake = FakeAdapter()
    await orch.handle(_ev("alice", "eng", "deploy uses the deploy-staging workflow", "1"), fake)
    await orch.handle(_ev("bob", "eng", "what did alice say about deploy?", "2"), fake)
    await orch.handle(_ev("carol", "sales", "hello team", "3"), fake)

    assert len(store.memory_search("console:eng", "")) == 2     # two eng turns
    assert len(store.memory_search("console:sales", "")) == 1   # isolated
    assert store.memory_search("console:sales", "deploy") == [] or all(
        "deploy" not in m.content for m in store.memory_search("console:sales", "deploy")
    )

    # bob's turn (2nd in eng) saw alice's prior note
    assert "remember" in fake.sent[1][1]

    users = {u.display_name for u in store.list_users("org1")}
    assert {"alice", "bob", "carol"} <= users


async def test_idempotency_skips_duplicate_message_id():
    store, orch = _build()
    fake = FakeAdapter()
    await orch.handle(_ev("alice", "eng", "hi", "dup"), fake)
    await orch.handle(_ev("alice", "eng", "hi again", "dup"), fake)
    assert len(fake.sent) == 1
