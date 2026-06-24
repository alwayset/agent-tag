from agent_tag.models import Role
from agent_tag.store.memory_store import InMemoryStore
from agent_tag.workspace.service import WorkspaceService


def _svc():
    ws = WorkspaceService(InMemoryStore())
    org = ws.create_org("Org", org_id="org1")
    workspace = ws.create_workspace(org.id, "WS", ws_id="ws1")
    return ws, org, workspace


def test_user_autoenroll_and_identity_resolution():
    ws, org, _ = _svc()
    u1 = ws.resolve_user(org.id, "lark", "ou_alice", "Alice")
    # same identity → same user
    u1b = ws.resolve_user(org.id, "lark", "ou_alice", "Alice")
    assert u1.id == u1b.id
    assert u1.role == Role.MEMBER
    # different identity → different user
    u2 = ws.resolve_user(org.id, "lark", "ou_bob", "Bob")
    assert u2.id != u1.id
    assert {u.display_name for u in ws.store.list_users(org.id)} == {"Alice", "Bob"}


def test_link_identity_across_platforms():
    ws, org, _ = _svc()
    alice = ws.resolve_user(org.id, "lark", "ou_alice", "Alice")
    ws.link_identity(alice.id, "slack", "U_ALICE")
    same = ws.resolve_user(org.id, "slack", "U_ALICE", "Alice")
    assert same.id == alice.id


def test_bind_channel_is_idempotent():
    ws, _, workspace = _svc()
    ch1, p1 = ws.bind_channel(workspace.id, "lark", "oc_eng", "eng")
    ch2, p2 = ws.bind_channel(workspace.id, "lark", "oc_eng", "eng")
    assert ch1.id == ch2.id
    assert p1.memory_namespace == "lark:oc_eng" == p2.memory_namespace
