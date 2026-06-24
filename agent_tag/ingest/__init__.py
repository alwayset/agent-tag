"""Corpus ingestion: crawl an org's existing Lark knowledge and index it for
query-time retrieval — the differentiator Claude Tag doesn't provide."""

from agent_tag.ingest.crawler import CrawledDoc, crawl_wiki_space, list_wiki_spaces
from agent_tag.ingest.indexer import chunk_text, ingest_wiki_space

__all__ = ["CrawledDoc", "crawl_wiki_space", "list_wiki_spaces", "chunk_text", "ingest_wiki_space"]
