"""Lark adapter PURE helpers — the @mention-token regex and _extract_files.

We deliberately do NOT construct a full P2ImMessageReceiveV1 / drive _normalize():
that SDK model is awkward to build by hand and constructing it adds no coverage
of OUR logic beyond these two helpers. So we test the helpers directly. The rest
of the adapter is I/O (WebSocket + HTTP to Lark) and is exercised live, not in unit
tests. Requires lark-oapi to be importable (it is, in the dev venv).
"""

from __future__ import annotations

from agent_tag.adapters.base import FileRef
from agent_tag.adapters.lark import _MENTION_TOKEN_RE, LarkAdapter


def _strip(text: str) -> str:
    """Mirror the normalize() mention-stripping step in isolation."""
    import re

    text = _MENTION_TOKEN_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def test_mention_token_regex_strips_user_and_all_tokens():
    assert _MENTION_TOKEN_RE.sub("", "@_user_1 hello there") == " hello there"
    assert _MENTION_TOKEN_RE.sub("", "ping @_all_1 now") == "ping  now"
    # multiple mention tokens in one message
    assert _MENTION_TOKEN_RE.sub("", "@_user_1 @_user_2 sync up") == "  sync up"


def test_mention_strip_collapses_whitespace():
    assert _strip("@_user_1 hello there") == "hello there"
    assert _strip("@_user_1   @_user_2   deploy now") == "deploy now"
    assert _strip("no mention here") == "no mention here"


def test_mention_regex_leaves_plain_at_text_alone():
    # a literal "@channel" or an email is NOT a Lark mention placeholder
    assert _MENTION_TOKEN_RE.sub("", "email me at a@b.com") == "email me at a@b.com"
    assert _MENTION_TOKEN_RE.sub("", "@channel meeting") == "@channel meeting"


def test_extract_files_image_encodes_message_id_and_type():
    refs = LarkAdapter._extract_files("image", '{"image_key": "img_xyz"}', "om_123")
    assert len(refs) == 1
    ref = refs[0]
    assert isinstance(ref, FileRef)
    # message_id is encoded into file_key as "<message_id>|<resource_key>"
    assert ref.file_key == "om_123|img_xyz"
    assert ref.mime == "image"
    assert ref.name is None


def test_extract_files_file_carries_name():
    refs = LarkAdapter._extract_files(
        "file", '{"file_key": "file_abc", "file_name": "report.pdf"}', "om_9"
    )
    assert refs[0].file_key == "om_9|file_abc"
    assert refs[0].mime == "file"
    assert refs[0].name == "report.pdf"


def test_extract_files_missing_key_returns_empty():
    assert LarkAdapter._extract_files("image", "{}", "om_1") == []
    assert LarkAdapter._extract_files("file", '{"file_name": "x"}', "om_1") == []


def test_extract_files_bad_json_is_safe():
    assert LarkAdapter._extract_files("image", "not json", "om_1") == []
    assert LarkAdapter._extract_files("file", "", "om_1") == []
