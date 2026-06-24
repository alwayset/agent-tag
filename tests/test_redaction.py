from agent_tag.core.redaction import Redactor


def test_redacts_api_keys_and_can_disable():
    r = Redactor(enabled=True)
    clean, n = r.redact("token is sk-abcdef012345678901234 ok")
    assert "sk-abcdef012345678901234" not in clean
    assert n == 1

    off = Redactor(enabled=False)
    text = "token is sk-abcdef012345678901234"
    assert off.redact(text) == (text, 0)


def test_no_match_is_passthrough():
    r = Redactor(enabled=True)
    assert r.redact("hello team") == ("hello team", 0)
