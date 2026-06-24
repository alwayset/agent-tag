"""The capability fence: memory must never cross a channel namespace, and the
scoped handle must expose no way to target another namespace."""

from agent_tag.core.memory import MemoryService, ScopedMemory
from agent_tag.store.memory_store import InMemoryStore


def test_namespace_fence_blocks_cross_channel_reads():
    mem = MemoryService(InMemoryStore())
    eng = mem.bind("lark:oc_eng")
    sales = mem.bind("lark:oc_sales")

    eng.write("staging deploy uses the deploy-staging workflow", kind="fact")

    assert len(eng.search("deploy")) == 1
    # sales is a different channel → sees nothing, regardless of query
    assert sales.search("deploy") == []
    assert sales.search("") == []
    assert sales.search("staging deploy workflow") == []


def test_scoped_handle_has_no_namespace_parameter():
    # The agent-facing tool is backed by ScopedMemory; search/write take no
    # namespace arg, so a prompt-injected agent cannot phrase a cross-channel query.
    import inspect

    for fn in (ScopedMemory.search, ScopedMemory.write):
        params = set(inspect.signature(fn).parameters) - {"self"}
        assert "namespace" not in params, f"{fn.__name__} must not accept a namespace"


def test_write_stays_in_its_namespace():
    store = InMemoryStore()
    mem = MemoryService(store)
    mem.bind("a").write("secret A")
    mem.bind("b").write("secret B")
    assert [m.content for m in store.memory_search("a", "")] == ["secret A"]
    assert [m.content for m in store.memory_search("b", "")] == ["secret B"]
