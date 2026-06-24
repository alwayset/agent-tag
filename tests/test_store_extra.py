"""Store coverage shared across InMemoryStore and SqliteStore: corpus workspace
fencing, corpus_docs / corpus_count, memory namespace isolation, and usage
accumulation. Parametrized so both implementations must agree."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager

import pytest

from agent_tag.models import CorpusChunk, MemoryItem
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.store.sqlite_store import SqliteStore


@contextmanager
def _store(kind):
    if kind == "memory":
        yield InMemoryStore()
        return
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield SqliteStore(path)
    finally:
        os.remove(path)


KINDS = ["memory", "sqlite"]


def _seed_corpus(store):
    store.corpus_add(CorpusChunk("ws1", "src:a", "d1", "Alpha", "u/d1", 0, "alpha deploy guide"))
    store.corpus_add(CorpusChunk("ws1", "src:a", "d1", "Alpha", "u/d1", 1, "alpha second chunk"))
    store.corpus_add(CorpusChunk("ws1", "src:b", "d2", "Beta", "u/d2", 0, "beta onboarding notes"))
    store.corpus_add(CorpusChunk("ws2", "src:a", "d9", "Gamma", "u/d9", 0, "gamma deploy secrets"))


@pytest.mark.parametrize("kind", KINDS)
def test_corpus_search_is_workspace_fenced(kind):
    with _store(kind) as store:
        _seed_corpus(store)
        hits = store.corpus_search("ws1", "deploy")
        assert hits  # ws1 has a deploy doc
        assert all(h.workspace_id == "ws1" for h in hits)
        # ws2's "gamma deploy secrets" must never appear for ws1
        assert all("gamma" not in h.text for h in hits)


@pytest.mark.parametrize("kind", KINDS)
def test_corpus_empty_query_returns_nothing(kind):
    with _store(kind) as store:
        _seed_corpus(store)
        assert store.corpus_search("ws1", "") == []
        assert store.corpus_search("ws1", "   ") == []


@pytest.mark.parametrize("kind", KINDS)
def test_corpus_docs_and_count(kind):
    with _store(kind) as store:
        _seed_corpus(store)
        assert store.corpus_count("ws1") == 3  # 2 chunks of d1 + 1 of d2
        assert store.corpus_count("ws2") == 1
        docs = {d["title"]: d for d in store.corpus_docs("ws1")}
        assert set(docs) == {"Alpha", "Beta"}
        assert docs["Alpha"]["chunks"] == 2
        assert docs["Beta"]["chunks"] == 1
        assert docs["Alpha"]["source"] == "src:a"


@pytest.mark.parametrize("kind", KINDS)
def test_corpus_clear_by_source_then_all(kind):
    with _store(kind) as store:
        _seed_corpus(store)
        store.corpus_clear("ws1", source="src:b")  # drop only Beta
        assert {d["title"] for d in store.corpus_docs("ws1")} == {"Alpha"}
        assert store.corpus_count("ws2") == 1  # untouched
        store.corpus_clear("ws1")  # drop the rest of ws1
        assert store.corpus_count("ws1") == 0
        assert store.corpus_count("ws2") == 1


@pytest.mark.parametrize("kind", KINDS)
def test_memory_namespace_isolation(kind):
    with _store(kind) as store:
        store.memory_write(MemoryItem("m1", "ns:eng", "fact", "eng secret note", "u", 1.0))
        store.memory_write(MemoryItem("m2", "ns:sales", "fact", "sales note", "u", 2.0))
        # each namespace sees only its own items, for any query
        assert [m.content for m in store.memory_search("ns:eng", "")] == ["eng secret note"]
        assert [m.content for m in store.memory_search("ns:sales", "note")] == ["sales note"]
        # cross-namespace query for the other's content returns nothing
        assert store.memory_search("ns:sales", "eng secret") == [] or all(
            "eng secret" not in m.content for m in store.memory_search("ns:sales", "eng secret")
        )


@pytest.mark.parametrize("kind", KINDS)
def test_usage_accumulates(kind):
    with _store(kind) as store:
        assert store.get_usage("c1").total == 0  # default zero before any add
        store.add_usage("c1", 10, 5)
        store.add_usage("c1", 3, 2)
        u = store.get_usage("c1")
        assert u.input_tokens == 13 and u.output_tokens == 7 and u.total == 20
        # a second channel is independent
        store.add_usage("c2", 1, 1)
        assert store.get_usage("c2").total == 2
        assert {x.channel_id for x in store.list_usage()} == {"c1", "c2"}
