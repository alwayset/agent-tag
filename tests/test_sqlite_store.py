"""SqliteStore: persistence + the namespace fence survive a reopen."""

import os
import tempfile

from agent_tag.models import ChannelPolicy, MemoryItem, Organization
from agent_tag.store.sqlite_store import SqliteStore


def _tmpdb():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def test_persists_across_reopen():
    path = _tmpdb()
    try:
        s = SqliteStore(path)
        s.put_org(Organization("org1", "Acme"))
        s.put_policy(
            ChannelPolicy(
                channel_id="c1",
                memory_namespace="lark:oc1",
                backend="claude",
                token_budget=5000,
                ambient_enabled=True,
            )
        )
        s.memory_write(MemoryItem("m1", "lark:oc1", "fact", "deploys on fridays", "u1", 1.0))
        s.set_setting("default_backend", "claude")
        s.add_usage("c1", 100, 50)

        s2 = SqliteStore(path)  # reopen
        assert s2.get_org("org1").name == "Acme"
        p = s2.get_policy("c1")
        assert p.backend == "claude" and p.token_budget == 5000 and p.ambient_enabled is True
        assert s2.get_setting("default_backend") == "claude"
        assert s2.get_usage("c1").total == 150
        assert [m.content for m in s2.list_memory("lark:oc1")] == ["deploys on fridays"]
    finally:
        os.remove(path)


def test_memory_fence_in_sqlite():
    path = _tmpdb()
    try:
        s = SqliteStore(path)
        s.memory_write(MemoryItem("m1", "lark:eng", "fact", "secret eng note", "u", 1.0))
        assert (
            s.memory_search("lark:eng", "secret") and s.memory_search("lark:sales", "secret") == []
        )
    finally:
        os.remove(path)


def test_memory_edit_delete():
    path = _tmpdb()
    try:
        s = SqliteStore(path)
        s.memory_write(MemoryItem("m1", "ns", "fact", "old", "u", 1.0))
        assert s.update_memory("m1", "new") is True
        assert s.get_memory("m1").content == "new"
        assert s.delete_memory("m1") is True
        assert s.get_memory("m1") is None
    finally:
        os.remove(path)
