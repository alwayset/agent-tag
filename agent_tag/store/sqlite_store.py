"""SqliteStore — the default persistent store: one file, zero infrastructure.

This is what makes the teammate's memory (the 智库 entity) survive restarts.
Same capability-fence contract as the in-memory store. Swap for Postgres+pgvector
when the corpus-ingestion milestone lands (see TODO.md).
"""
from __future__ import annotations

import json
import sqlite3
import threading

from agent_tag.models import (
    AuditEvent,
    Channel,
    ChannelPolicy,
    MemoryItem,
    Organization,
    Role,
    TokenUsage,
    User,
    Workspace,
)
from agent_tag.store.base import Store

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, org_id TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, org_id TEXT, display_name TEXT, role TEXT, identities TEXT);
CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY, workspace_id TEXT, platform TEXT, external_id TEXT, name TEXT,
  UNIQUE(platform, external_id));
CREATE TABLE IF NOT EXISTS policies (
  channel_id TEXT PRIMARY KEY, memory_namespace TEXT, backend TEXT, model TEXT,
  allowed_tools TEXT, redaction_enabled INT, ambient_enabled INT, ambient_interval_hours INT,
  require_mention INT, admin_user_ids TEXT, token_budget INT, display_name TEXT);
CREATE TABLE IF NOT EXISTS memory (
  id TEXT PRIMARY KEY, namespace TEXT, kind TEXT, content TEXT, provenance TEXT,
  created_at REAL, decay_at REAL);
CREATE INDEX IF NOT EXISTS idx_memory_ns ON memory(namespace);
CREATE TABLE IF NOT EXISTS audit (
  id TEXT PRIMARY KEY, ts REAL, channel_id TEXT, actor TEXT, requested_by TEXT,
  action TEXT, detail TEXT, outcome TEXT);
CREATE INDEX IF NOT EXISTS idx_audit_ch ON audit(channel_id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS usage (
  channel_id TEXT PRIMARY KEY, input_tokens INT DEFAULT 0, output_tokens INT DEFAULT 0);
"""


class SqliteStore(Store):
    def __init__(self, path: str = "agent_tag.db") -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # --- helpers ---
    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    # --- orgs / workspaces ---
    def put_org(self, org: Organization) -> None:
        self._exec("INSERT OR REPLACE INTO orgs(id,name) VALUES(?,?)", (org.id, org.name))

    def get_org(self, org_id: str) -> Organization | None:
        r = self._query("SELECT * FROM orgs WHERE id=?", (org_id,))
        return Organization(r[0]["id"], r[0]["name"]) if r else None

    def list_orgs(self) -> list[Organization]:
        return [Organization(r["id"], r["name"]) for r in self._query("SELECT * FROM orgs")]

    def put_workspace(self, ws: Workspace) -> None:
        self._exec("INSERT OR REPLACE INTO workspaces(id,org_id,name) VALUES(?,?,?)",
                   (ws.id, ws.org_id, ws.name))

    def get_workspace(self, ws_id: str) -> Workspace | None:
        r = self._query("SELECT * FROM workspaces WHERE id=?", (ws_id,))
        return Workspace(r[0]["id"], r[0]["org_id"], r[0]["name"]) if r else None

    def list_workspaces(self, org_id: str | None = None) -> list[Workspace]:
        if org_id:
            rows = self._query("SELECT * FROM workspaces WHERE org_id=?", (org_id,))
        else:
            rows = self._query("SELECT * FROM workspaces")
        return [Workspace(r["id"], r["org_id"], r["name"]) for r in rows]

    # --- users ---
    def _user(self, r: sqlite3.Row) -> User:
        return User(r["id"], r["org_id"], r["display_name"], Role(r["role"]),
                    json.loads(r["identities"] or "{}"))

    def put_user(self, user: User) -> None:
        self._exec(
            "INSERT OR REPLACE INTO users(id,org_id,display_name,role,identities) VALUES(?,?,?,?,?)",
            (user.id, user.org_id, user.display_name, user.role.value, json.dumps(user.identities)))

    def get_user(self, user_id: str) -> User | None:
        r = self._query("SELECT * FROM users WHERE id=?", (user_id,))
        return self._user(r[0]) if r else None

    def find_user_by_identity(self, platform: str, external_user_id: str) -> User | None:
        for r in self._query("SELECT * FROM users"):
            if json.loads(r["identities"] or "{}").get(platform) == external_user_id:
                return self._user(r)
        return None

    def list_users(self, org_id: str) -> list[User]:
        return [self._user(r) for r in self._query("SELECT * FROM users WHERE org_id=?", (org_id,))]

    # --- channels / policy ---
    def _channel(self, r: sqlite3.Row) -> Channel:
        return Channel(r["id"], r["workspace_id"], r["platform"], r["external_id"], r["name"])

    def put_channel(self, ch: Channel) -> None:
        self._exec(
            "INSERT OR REPLACE INTO channels(id,workspace_id,platform,external_id,name) VALUES(?,?,?,?,?)",
            (ch.id, ch.workspace_id, ch.platform, ch.external_id, ch.name))

    def get_channel(self, channel_id: str) -> Channel | None:
        r = self._query("SELECT * FROM channels WHERE id=?", (channel_id,))
        return self._channel(r[0]) if r else None

    def find_channel(self, platform: str, external_id: str) -> Channel | None:
        r = self._query("SELECT * FROM channels WHERE platform=? AND external_id=?",
                        (platform, external_id))
        return self._channel(r[0]) if r else None

    def list_channels(self, workspace_id: str | None = None) -> list[Channel]:
        if workspace_id:
            rows = self._query("SELECT * FROM channels WHERE workspace_id=?", (workspace_id,))
        else:
            rows = self._query("SELECT * FROM channels")
        return [self._channel(r) for r in rows]

    def put_policy(self, p: ChannelPolicy) -> None:
        self._exec(
            """INSERT OR REPLACE INTO policies(channel_id,memory_namespace,backend,model,
               allowed_tools,redaction_enabled,ambient_enabled,ambient_interval_hours,
               require_mention,admin_user_ids,token_budget,display_name)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p.channel_id, p.memory_namespace, p.backend, p.model, json.dumps(p.allowed_tools),
             int(p.redaction_enabled), int(p.ambient_enabled), p.ambient_interval_hours,
             int(p.require_mention), json.dumps(p.admin_user_ids), p.token_budget, p.display_name))

    def get_policy(self, channel_id: str) -> ChannelPolicy | None:
        r = self._query("SELECT * FROM policies WHERE channel_id=?", (channel_id,))
        if not r:
            return None
        x = r[0]
        return ChannelPolicy(
            channel_id=x["channel_id"], memory_namespace=x["memory_namespace"],
            backend=x["backend"], model=x["model"],
            allowed_tools=json.loads(x["allowed_tools"] or "[]"),
            redaction_enabled=bool(x["redaction_enabled"]),
            ambient_enabled=bool(x["ambient_enabled"]),
            ambient_interval_hours=x["ambient_interval_hours"] or 24,
            require_mention=bool(x["require_mention"]),
            admin_user_ids=json.loads(x["admin_user_ids"] or "[]"),
            token_budget=x["token_budget"], display_name=x["display_name"] or "")

    # --- memory ---
    def _mem(self, r: sqlite3.Row) -> MemoryItem:
        return MemoryItem(r["id"], r["namespace"], r["kind"], r["content"], r["provenance"],
                          r["created_at"], r["decay_at"])

    def memory_write(self, item: MemoryItem) -> None:
        self._exec(
            "INSERT OR REPLACE INTO memory(id,namespace,kind,content,provenance,created_at,decay_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (item.id, item.namespace, item.kind, item.content, item.provenance,
             item.created_at, item.decay_at))

    def memory_search(self, namespace: str, query: str, limit: int = 10) -> list[MemoryItem]:
        # the fence: only this namespace's rows are ever loaded
        rows = self._query("SELECT * FROM memory WHERE namespace=?", (namespace,))
        items = [self._mem(r) for r in rows]
        q = query.lower().strip()
        if not q:
            items.sort(key=lambda m: m.created_at, reverse=True)
        else:
            terms = set(q.split())
            items.sort(key=lambda m: (sum(t in m.content.lower() for t in terms), m.created_at),
                       reverse=True)
        return items[:limit]

    def list_memory(self, namespace: str, limit: int = 200) -> list[MemoryItem]:
        rows = self._query(
            "SELECT * FROM memory WHERE namespace=? ORDER BY created_at DESC LIMIT ?",
            (namespace, limit))
        return [self._mem(r) for r in rows]

    def get_memory(self, item_id: str) -> MemoryItem | None:
        r = self._query("SELECT * FROM memory WHERE id=?", (item_id,))
        return self._mem(r[0]) if r else None

    def update_memory(self, item_id: str, content: str) -> bool:
        if not self.get_memory(item_id):
            return False
        self._exec("UPDATE memory SET content=? WHERE id=?", (content, item_id))
        return True

    def delete_memory(self, item_id: str) -> bool:
        if not self.get_memory(item_id):
            return False
        self._exec("DELETE FROM memory WHERE id=?", (item_id,))
        return True

    # --- audit ---
    def append_audit(self, e: AuditEvent) -> None:
        self._exec(
            "INSERT OR REPLACE INTO audit(id,ts,channel_id,actor,requested_by,action,detail,outcome)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (e.id, e.ts, e.channel_id, e.actor, e.requested_by, e.action, e.detail, e.outcome))

    def list_audit(self, channel_id: str | None = None, limit: int = 200) -> list[AuditEvent]:
        if channel_id:
            rows = self._query(
                "SELECT * FROM audit WHERE channel_id=? ORDER BY ts DESC LIMIT ?",
                (channel_id, limit))
        else:
            rows = self._query("SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,))
        return [AuditEvent(r["id"], r["ts"], r["channel_id"], r["actor"], r["requested_by"],
                           r["action"], r["detail"], r["outcome"]) for r in rows]

    # --- settings ---
    def get_setting(self, key: str) -> str | None:
        r = self._query("SELECT value FROM settings WHERE key=?", (key,))
        return r[0]["value"] if r else None

    def set_setting(self, key: str, value: str) -> None:
        self._exec("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))

    def all_settings(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self._query("SELECT * FROM settings")}

    # --- usage ---
    def add_usage(self, channel_id: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage(channel_id,input_tokens,output_tokens) VALUES(?,?,?) "
                "ON CONFLICT(channel_id) DO UPDATE SET "
                "input_tokens=input_tokens+excluded.input_tokens, "
                "output_tokens=output_tokens+excluded.output_tokens",
                (channel_id, input_tokens, output_tokens))
            self._conn.commit()

    def get_usage(self, channel_id: str) -> TokenUsage:
        r = self._query("SELECT * FROM usage WHERE channel_id=?", (channel_id,))
        if not r:
            return TokenUsage(channel_id=channel_id)
        return TokenUsage(channel_id, r[0]["input_tokens"], r[0]["output_tokens"])

    def list_usage(self) -> list[TokenUsage]:
        return [TokenUsage(r["channel_id"], r["input_tokens"], r["output_tokens"])
                for r in self._query("SELECT * FROM usage")]
