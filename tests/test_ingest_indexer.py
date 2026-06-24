"""Ingest pipeline: chunk_text sizing/overlap/empty, and ingest_wiki_space wired
to a FAKE crawler (no network, no lark-cli) so we can assert the corpus rows and
source tagging the indexer produces."""

from __future__ import annotations

import agent_tag.ingest.indexer as indexer
from agent_tag.ingest.crawler import CrawledDoc, CrawlResult
from agent_tag.ingest.indexer import chunk_text, ingest_wiki_space
from agent_tag.store.memory_store import InMemoryStore


def test_chunk_text_empty_and_whitespace():
    assert chunk_text("") == []
    assert chunk_text("   \n  \n") == []


def test_chunk_text_keeps_short_text_whole():
    assert chunk_text("just one short line") == ["just one short line"]


def test_chunk_text_groups_paragraphs_under_target():
    text = "\n".join(["para one", "para two", "para three"])
    chunks = chunk_text(text, target=1000)
    assert chunks == ["para one\npara two\npara three"]  # all fit in one chunk


def test_chunk_text_splits_when_over_target():
    text = "\n".join(f"paragraph {i} with several words here" for i in range(200))
    chunks = chunk_text(text, target=200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 + 40 for c in chunks)  # ~target with paragraph slack


def test_chunk_text_hard_splits_a_single_huge_paragraph_with_overlap():
    # distinguishable content (digits) so the overlap check isn't vacuous
    huge = "".join(str(i % 10) for i in range(2500))
    chunks = chunk_text(huge, target=1000, overlap=120)
    assert len(chunks) == 3  # 2500 over a 880-char stride
    assert all(len(c) <= 1000 for c in chunks)
    # consecutive chunks overlap by exactly (target - overlap was the stride):
    # chunk[1] starts at index 880, so chunk[0][880:] == chunk[1][:120]
    assert chunks[0][880:] == chunks[1][:120]
    # joined length exceeds the source precisely because of the duplicated overlap
    assert len("".join(chunks)) > len(huge)


def _fake_result():
    return CrawlResult(
        docs=[
            CrawledDoc(
                doc_id="doc_a",
                title="Compliance Policy",
                obj_type="docx",
                node_token="node_a",
                url="https://wiki/node_a",
                text="\n".join(f"compliance line {i}" for i in range(50)),
            ),
            CrawledDoc(
                doc_id="doc_b",
                title="Onboarding",
                obj_type="docx",
                node_token="node_b",
                url="https://wiki/node_b",
                text="new hires get a laptop and a Lark account",
            ),
        ],
        skipped=[("A Spreadsheet", "sheet")],
    )


def test_ingest_wiki_space_writes_corpus_with_fake_crawler(monkeypatch):
    captured = {}

    def fake_crawl(cli, space_id, *, domain="https://open.larksuite.com", **kw):
        captured["space_id"] = space_id
        captured["domain"] = domain
        return _fake_result()

    # The indexer imported crawl_wiki_space into its own namespace; patch there.
    monkeypatch.setattr(indexer, "crawl_wiki_space", fake_crawl)

    store = InMemoryStore()
    stats = ingest_wiki_space(
        store,
        workspace_id="ws1",
        space_id="space123",
        cli=object(),  # any non-None cli; the fake crawler ignores it
        space_name="Eng Wiki",
        domain="https://open.feishu.cn",
    )

    assert captured["space_id"] == "space123"
    assert captured["domain"] == "https://open.feishu.cn"
    assert stats["docs"] == 2
    assert stats["chunks"] >= 2
    assert stats["skipped"] == 1
    assert stats["source"] == "lark-wiki:space123"
    assert stats["space_name"] == "Eng Wiki"

    # Corpus rows landed in the right workspace, tagged with the wiki source.
    assert store.corpus_count("ws1") == stats["chunks"]
    titles = {d["title"] for d in store.corpus_docs("ws1")}
    assert titles == {"Compliance Policy", "Onboarding"}
    for d in store.corpus_docs("ws1"):
        assert d["source"] == "lark-wiki:space123"
    # The ingested text is now retrievable, fenced to ws1.
    hits = store.corpus_search("ws1", "laptop")
    assert hits and hits[0].title == "Onboarding"
    assert store.corpus_search("ws2", "laptop") == []  # other workspace sees nothing


def test_ingest_wiki_space_replaces_on_reingest(monkeypatch):
    monkeypatch.setattr(indexer, "crawl_wiki_space", lambda *a, **k: _fake_result())
    store = InMemoryStore()
    first = ingest_wiki_space(store, "ws1", "space123", cli=object())
    again = ingest_wiki_space(store, "ws1", "space123", cli=object())
    # re-ingest clears the prior source rows first → count does not double
    assert store.corpus_count("ws1") == first["chunks"] == again["chunks"]
