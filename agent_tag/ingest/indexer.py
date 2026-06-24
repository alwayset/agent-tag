"""Chunk crawled docs and write them into the store's corpus index."""
from __future__ import annotations

from agent_tag.ingest.crawler import CrawlResult, crawl_wiki_space
from agent_tag.lark_cli import LarkCli
from agent_tag.models import CorpusChunk
from agent_tag.store.base import Store


def chunk_text(text: str, *, target: int = 1000, overlap: int = 120) -> list[str]:
    """Paragraph-aware chunking to ~`target` chars with a little overlap."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= target:
            buf = f"{buf}\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= target:
                buf = p
            else:  # a single huge paragraph: hard-split
                for i in range(0, len(p), target - overlap):
                    chunks.append(p[i:i + target])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def index_crawl(store: Store, workspace_id: str, source: str, result: CrawlResult) -> dict:
    store.corpus_clear(workspace_id, source)   # re-ingest = replace
    n_chunks = 0
    for doc in result.docs:
        for i, ch in enumerate(chunk_text(doc.text)):
            store.corpus_add(CorpusChunk(
                workspace_id=workspace_id, source=source, doc_id=doc.doc_id,
                title=doc.title, url=doc.url, chunk_idx=i, text=ch))
            n_chunks += 1
    return {"docs": len(result.docs), "chunks": n_chunks, "skipped": len(result.skipped)}


def ingest_wiki_space(store: Store, workspace_id: str, space_id: str, *,
                      cli: LarkCli | None = None, space_name: str = "",
                      domain: str = "https://open.larksuite.com") -> dict:
    cli = cli or LarkCli()
    result = crawl_wiki_space(cli, space_id, domain=domain)
    source = f"lark-wiki:{space_id}"
    stats = index_crawl(store, workspace_id, source, result)
    stats.update({"space_id": space_id, "space_name": space_name, "source": source})
    return stats
