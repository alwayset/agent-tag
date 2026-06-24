"""Crawl a Lark wiki space → flat list of documents with plain text.

Walks the wiki node tree (recursing on has_child) and pulls docx raw_content.
Non-text node types (sheets/bitable/mindnote/files) are reported as skipped for
now — extending readers is a TODO. Uses the LarkCli wrapper (user identity), so
it respects the authorizing user's permissions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_tag.lark_cli import LarkCli

_TEXT_TYPES = {"docx", "doc"}


@dataclass(slots=True)
class CrawledDoc:
    doc_id: str          # obj_token
    title: str
    obj_type: str
    node_token: str
    url: str
    text: str


@dataclass(slots=True)
class CrawlResult:
    docs: list[CrawledDoc] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (title, obj_type)


def list_wiki_spaces(cli: LarkCli) -> list[dict]:
    """Return [{space_id, name, ...}] for the authorized user."""
    return cli.paged("GET", "/open-apis/wiki/v2/spaces", params={"page_size": 50})


def _list_nodes(cli: LarkCli, space_id: str, parent: str | None = None) -> list[dict]:
    params = {"page_size": 50}
    if parent:
        params["parent_node_token"] = parent
    return cli.paged("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes", params=params)


def _fetch_docx_text(cli: LarkCli, document_id: str) -> str:
    payload = cli.api("GET", f"/open-apis/docx/v1/documents/{document_id}/raw_content",
                      params={"lang": 0})
    return (payload.get("data", {}) or {}).get("content", "") or ""


def crawl_wiki_space(cli: LarkCli, space_id: str, *, domain: str = "https://open.larksuite.com",
                     max_nodes: int = 500) -> CrawlResult:
    result = CrawlResult()
    host = domain.replace("/open-apis", "").rstrip("/")
    # BFS over the node tree
    queue: list[str | None] = [None]
    seen = 0
    while queue and seen < max_nodes:
        parent = queue.pop(0)
        for node in _list_nodes(cli, space_id, parent):
            seen += 1
            if seen > max_nodes:
                break
            title = node.get("title") or "(untitled)"
            obj_type = node.get("obj_type", "")
            obj_token = node.get("obj_token", "")
            node_token = node.get("node_token", "")
            if node.get("has_child"):
                queue.append(node_token)
            if obj_type in _TEXT_TYPES and obj_token:
                try:
                    text = _fetch_docx_text(cli, obj_token) if obj_type == "docx" else ""
                except Exception:  # noqa: BLE001 - one bad doc shouldn't kill the crawl
                    text = ""
                if text.strip():
                    result.docs.append(CrawledDoc(
                        doc_id=obj_token, title=title, obj_type=obj_type,
                        node_token=node_token, url=f"{host}/wiki/{node_token}", text=text))
                else:
                    result.skipped.append((title, obj_type or "empty"))
            else:
                result.skipped.append((title, obj_type or "node"))
    return result
