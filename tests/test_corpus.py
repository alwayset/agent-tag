"""Corpus ingestion: chunking + workspace-fenced retrieval on both stores."""

import os
import tempfile

import pytest

from agent_tag.ingest.indexer import chunk_text
from agent_tag.models import CorpusChunk
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.store.sqlite_store import SqliteStore


def test_chunk_text_splits_long_and_keeps_short():
    assert chunk_text("") == []
    assert chunk_text("short line") == ["short line"]
    big = "\n".join(f"paragraph number {i} with some words" for i in range(400))
    chunks = chunk_text(big, target=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1200 for c in chunks)  # ~target with paragraph slack


def _seed(store):
    store.corpus_add(
        CorpusChunk(
            "ws1",
            "lark-wiki:s1",
            "d1",
            "Deploy Guide",
            "http://x/d1",
            0,
            "staging deploy uses the deploy-staging workflow",
        )
    )
    store.corpus_add(
        CorpusChunk(
            "ws1",
            "lark-wiki:s1",
            "d2",
            "Onboarding",
            "http://x/d2",
            0,
            "new hires get a laptop and an email account",
        )
    )
    store.corpus_add(
        CorpusChunk(
            "ws2",
            "lark-wiki:s9",
            "d9",
            "Other Workspace",
            "http://x/d9",
            0,
            "deploy secrets for the other team",
        )
    )


@pytest.mark.parametrize("make", [lambda: InMemoryStore(), "sqlite"])
def test_corpus_search_is_workspace_fenced(make):
    if make == "sqlite":
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        store = SqliteStore(path)
    else:
        store = make()
        path = None
    try:
        _seed(store)
        hits = store.corpus_search("ws1", "deploy", limit=5)
        assert hits and all(h.workspace_id == "ws1" for h in hits)
        # ws2's "deploy secrets" doc must never surface for ws1
        assert all("other team" not in h.text for h in hits)
        assert store.corpus_count("ws1") == 2
        assert store.corpus_search("ws2", "deploy")  # ws2 has its own
        assert {d["title"] for d in store.corpus_docs("ws1")} == {"Deploy Guide", "Onboarding"}
        removed = store.corpus_clear("ws1")
        assert removed >= 0  # in-memory returns count; both clear ws1
        assert store.corpus_count("ws1") == 0
        assert store.corpus_count("ws2") == 1  # untouched
    finally:
        if path:
            os.remove(path)
