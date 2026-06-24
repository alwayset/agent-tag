"""TurnOrchestrator.handle() behaviors, end to end against InMemoryStore + EchoBackend.

A FakeAdapter records every send() so we can assert on exactly what the channel
saw. A UsageEchoBackend lets us drive the token-budget kill-switch deterministically.
These cover the per-turn governance path: onboarding, the mention gate, grounded
replies, redaction, the memory note, corpus blending, budget, and idempotency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from agent_tag.adapters.base import Adapter, InboundEvent
from agent_tag.backends.base import BackendAdapter, Delta, TurnRequest, Usage
from agent_tag.backends.echo import EchoBackend
from agent_tag.core.memory import MemoryService
from agent_tag.core.orchestrator import TurnOrchestrator
from agent_tag.core.redaction import Redactor
from agent_tag.core.router import Router
from agent_tag.models import CorpusChunk
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.workspace.service import WorkspaceService


class FakeAdapter(Adapter):
    platform = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str | None]] = []

    async def stream_inbound(self):
        if False:
            yield  # pragma: no cover

    async def send(self, channel_id, text, *, thread_id=None):
        self.sent.append((channel_id, text, thread_id))
        return "m1"


class RecordingEchoBackend(EchoBackend):
    """EchoBackend that captures the TurnRequest it was handed, so a test can
    assert what context (system prompt / metadata) the orchestrator assembled."""

    def __init__(self) -> None:
        super().__init__()
        self.last_req: TurnRequest | None = None

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        self.last_req = req
        async for delta in super().run_turn(req):
            yield delta


class FixedReplyBackend(BackendAdapter):
    """Streams a fixed reply and reports a fixed token usage — used to exercise
    redaction (reply containing a secret) and the budget meter."""

    name = "fixed"

    def __init__(self, reply: str, *, usage: Usage | None = None) -> None:
        self.reply = reply
        self._usage = usage or Usage()

    async def run_turn(self, req: TurnRequest) -> AsyncIterator[Delta]:
        yield Delta(type="text", text=self.reply)
        yield Delta(type="done")

    def report_usage(self) -> Usage:
        return self._usage


def _build(
    *,
    redaction=False,
    auto_bind=True,
    require_mention=True,
    backends=None,
    default_backend="echo",
):
    store = InMemoryStore()
    ws = WorkspaceService(store)
    org = ws.create_org("Org", org_id="org1")
    wsp = ws.create_workspace(org.id, "WS", ws_id="ws1")
    router = Router(
        ws,
        default_org_id=org.id,
        default_workspace_id=wsp.id,
        default_backend=default_backend,
        auto_bind=auto_bind,
        require_mention=require_mention,
    )
    orch = TurnOrchestrator(
        router=router,
        memory=MemoryService(store),
        redactor=Redactor(enabled=redaction),
        backends=backends if backends is not None else {"echo": EchoBackend()},
        default_backend=default_backend,
    )
    return store, ws, orch


def _ev(text="hi @bot", *, mentions=True, mid="1", channel="eng", user="alice"):
    return InboundEvent(
        platform="console",
        channel_id=channel,
        user_id=user,
        user_display_name=user,
        text=text,
        mentions_bot=mentions,
        message_id=mid,
    )


async def test_unbound_channel_gets_onboarding_reply():
    # auto_bind off → router returns None → orchestrator must send the onboarding line.
    store, _ws, orch = _build(auto_bind=False)
    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1
    _, text, _ = fake.sent[0]
    assert "isn't set up yet" in text
    # Nothing was bound, so no audit / memory should have been written.
    assert store.list_audit() == []


async def test_require_mention_gate_ignores_unmentioned():
    store, _ws, orch = _build(require_mention=True)
    fake = FakeAdapter()
    await orch.handle(_ev(mentions=False), fake)
    assert fake.sent == []  # silent: not mentioned in a require_mention channel


async def test_normal_grounded_reply_and_audit():
    store, _ws, orch = _build()
    fake = FakeAdapter()
    await orch.handle(_ev("what's the deploy plan? @bot"), fake)
    assert len(fake.sent) == 1
    _, text, _ = fake.sent[0]
    assert "echo backend" in text.lower()  # the backend produced the reply
    actions = {e.action for e in store.list_audit()}
    assert {"respond", "memory_write"} <= actions


async def test_redaction_is_applied_to_outbound():
    secret = "sk-abcdef0123456789abcd"
    backend = FixedReplyBackend(f"the key is {secret}")
    store, _ws, orch = _build(redaction=True, backends={"echo": backend})
    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    _, text, _ = fake.sent[0]
    assert secret not in text
    assert "[redacted]" in text
    # The audit detail records how many redactions happened.
    respond = [e for e in store.list_audit() if e.action == "respond"][0]
    assert "redactions=1" in respond.detail


async def test_memory_note_written_with_provenance():
    store, _ws, orch = _build()
    fake = FakeAdapter()
    await orch.handle(_ev("deploys happen on fridays @bot", user="alice"), fake)
    notes = store.memory_search("console:eng", "")
    assert len(notes) == 1
    note = notes[0]
    assert "alice said:" in note.content
    assert "deploys happen on fridays" in note.content
    assert note.kind == "interaction"
    # provenance is the resolved org user id, not a raw platform id
    assert note.provenance.startswith("usr_")


async def test_corpus_retrieval_is_blended_into_context_and_reply():
    backend = RecordingEchoBackend()
    store, _ws, orch = _build(backends={"echo": backend})
    store.corpus_add(
        CorpusChunk(
            "ws1",
            "lark-wiki:s1",
            "d1",
            "Deploy Runbook",
            "http://x/d1",
            0,
            "production deploy uses the deploy-prod workflow and requires two approvals",
        )
    )
    fake = FakeAdapter()
    await orch.handle(_ev("how do we deploy to production? @bot"), fake)

    # The backend saw the corpus doc both in the system prompt and in metadata.
    assert backend.last_req is not None
    assert "Deploy Runbook" in backend.last_req.system
    assert "Deploy Runbook" in backend.last_req.metadata["doc_titles"]
    # EchoBackend surfaces doc titles in its reply, so the channel sees it cited.
    _, text, _ = fake.sent[0]
    assert "Deploy Runbook" in text


async def test_corpus_retrieval_is_workspace_fenced_in_turn():
    backend = RecordingEchoBackend()
    store, _ws, orch = _build(backends={"echo": backend})
    # A doc that lives in a DIFFERENT workspace must never reach this channel's turn.
    store.corpus_add(
        CorpusChunk(
            "other-ws",
            "lark-wiki:s9",
            "d9",
            "Secret Other Doc",
            "http://x/d9",
            0,
            "production deploy secrets for the other team",
        )
    )
    fake = FakeAdapter()
    await orch.handle(_ev("how do we deploy to production? @bot"), fake)
    assert backend.last_req is not None
    assert "Secret Other Doc" not in backend.last_req.system
    assert backend.last_req.metadata["doc_titles"] == []


async def test_token_budget_kill_switch_blocks_and_audits_denied():
    backend = FixedReplyBackend("ok")
    store, ws, orch = _build(backends={"echo": backend})
    # bind first so we can set a budget on the policy before the turn
    ch, pol = ws.bind_channel("ws1", "console", "eng", "eng")
    pol.token_budget = 100
    store.put_policy(pol)
    store.add_usage(ch.id, 80, 40)  # 120 >= 100 → over budget

    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1
    _, text, _ = fake.sent[0]
    assert "token budget" in text.lower()
    denied = [e for e in store.list_audit(ch.id) if e.action == "denied"]
    assert denied and denied[0].outcome == "blocked"
    # blocked before generation → no memory note written
    assert store.memory_search(pol.memory_namespace, "") == []


async def test_under_budget_meters_usage_for_next_turn():
    backend = FixedReplyBackend("a reply", usage=Usage(input_tokens=30, output_tokens=12))
    store, ws, orch = _build(backends={"echo": backend})
    ch, pol = ws.bind_channel("ws1", "console", "eng", "eng")
    pol.token_budget = 1000
    store.put_policy(pol)

    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1
    assert store.get_usage(ch.id).total == 42  # this turn's usage recorded


async def test_idempotent_message_id_yields_one_response():
    store, _ws, orch = _build()
    fake = FakeAdapter()
    await orch.handle(_ev("first @bot", mid="dup"), fake)
    await orch.handle(_ev("second @bot", mid="dup"), fake)
    assert len(fake.sent) == 1  # second delivery of the same id is dropped


async def test_unconfigured_backend_explains_itself():
    # default backend missing from the registry → friendly error + audit error
    store, ws, orch = _build(backends={}, default_backend="echo")
    ch, _pol = ws.bind_channel("ws1", "console", "eng", "eng")
    fake = FakeAdapter()
    await orch.handle(_ev(), fake)
    assert len(fake.sent) == 1
    _, text, _ = fake.sent[0]
    assert "isn't configured" in text
    assert any(e.outcome == "error" for e in store.list_audit(ch.id))
