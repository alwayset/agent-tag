"""Admin web UI for Agent Tag.

A server-rendered FastAPI + Jinja2 console — no frontend build step. The whole UI
is driven off the already-built core services (store / settings / workspace), so
this package owns *zero* domain logic: it reads and writes through the existing
APIs only.

Import is safe without web extras at the package boundary: `create_app` imports
FastAPI/Jinja2 lazily inside the function, so `from agent_tag.web import create_app`
works on a bare install and only fails (with a clear message) when you actually
call it without `pip install 'agent-tag[web]'`.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# FastAPI resolves the string annotations on route handlers against this module's
# globals, so `Request` etc. must live at module scope. We import them eagerly but
# tolerate their absence, keeping `from agent_tag.web import create_app` importable
# on a bare install (the actual failure is raised inside create_app with a clear
# message). The web extra is required only to *call* create_app.
try:
    from fastapi import FastAPI, Request  # noqa: F401
    from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: F401

    _WEB_AVAILABLE = True
except ImportError:  # pragma: no cover - bare install path
    FastAPI = Request = HTMLResponse = RedirectResponse = None  # type: ignore[assignment, misc]
    _WEB_AVAILABLE = False

if TYPE_CHECKING:  # type-only — never imported at runtime on a bare install
    from agent_tag.app import CoreBundle
    from agent_tag.config import Config
    from agent_tag.settings import SettingsService

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"

COOKIE_NAME = "agent_tag_token"

# Sidebar is built from this — Channels points at the workspace page where
# channels are listed/created, and Memory at the memory picker.
NAV = [
    ("dashboard", "Dashboard", "/"),
    ("connections", "Connections", "/connections"),
    ("workspace", "Workspace", "/workspace"),
    ("channels", "Channels", "/workspace"),
    ("knowledge", "Knowledge", "/knowledge"),
    ("memory", "Memory", "/memory"),
    ("audit", "Audit", "/audit"),
    ("usage", "Usage", "/usage"),
]


def _fmt_ts(value: Any) -> str:
    """Render a float epoch (or None) as a friendly local timestamp."""
    if value in (None, "", 0):
        return "—"
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError, TypeError):
        return str(value)


def create_app(core: "CoreBundle", settings: "SettingsService", config: "Config") -> "FastAPI":
    """Build the admin FastAPI app wired to an already-constructed core bundle.

    `core`     — CoreBundle (store / workspace / backends / org & workspace ids)
    `settings` — SettingsService (Connections page + checklist)
    `config`   — effective Config (admin_token gates auth; if falsy, no auth)
    """
    if not _WEB_AVAILABLE:
        raise ImportError(
            "the admin web UI needs the web extra — install it with "
            "`pip install 'agent-tag[web]'` (fastapi, uvicorn, jinja2, python-multipart)."
        )
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates

    from agent_tag.backends.registry import available as backends_available
    from agent_tag.models import ChannelPolicy, Role
    from agent_tag.settings import SETTING_SPECS

    store = core.store
    workspace = core.workspace
    admin_token = (config.admin_token or "").strip() or None

    templates = Jinja2Templates(directory=str(_TEMPLATES))
    templates.env.filters["ts"] = _fmt_ts

    app = FastAPI(title="Agent Tag — Admin", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    # ---------- helpers ----------

    def authed(request: Request) -> bool:
        if admin_token is None:
            return True
        return request.cookies.get(COOKIE_NAME) == admin_token

    def render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
        base = {
            "request": request,
            "nav": NAV,
            "active": ctx.pop("active", ""),
            "org": store.get_org(core.org_id),
            "auth_enabled": admin_token is not None,
        }
        base.update(ctx)
        return templates.TemplateResponse(request, template, base)

    def channel_label(ch) -> str:
        if ch is None:
            return "—"
        policy = store.get_policy(ch.id)
        if policy and policy.display_name:
            return policy.display_name
        return ch.name or ch.external_id

    def flash_redirect(url: str, message: str = "") -> RedirectResponse:
        if message:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}flash={message}"
        return RedirectResponse(url, status_code=303)

    # ---------- auth ----------

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, error: str = "", next: str = "/"):
        if admin_token is None:
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(
            request, "login.html",
            {"request": request, "error": error, "next": next},
        )

    @app.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        token = (form.get("token") or "").strip()
        nxt = form.get("next") or "/"
        if admin_token is None or token == admin_token:
            resp = RedirectResponse(nxt or "/", status_code=303)
            resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
            return resp
        return templates.TemplateResponse(
            request, "login.html",
            {"request": request, "error": "Incorrect token.", "next": nxt},
            status_code=401,
        )

    @app.get("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE_NAME)
        return resp

    def guard(request: Request) -> RedirectResponse | None:
        """Return a redirect to /login when auth is on and the cookie is missing/wrong."""
        if authed(request):
            return None
        nxt = request.url.path
        if request.url.query:
            nxt = f"{nxt}?{request.url.query}"
        return RedirectResponse(f"/login?next={nxt}", status_code=303)

    # ---------- 1. Dashboard ----------

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        channels = store.list_channels()
        users = store.list_users(core.org_id)

        mem_total = 0
        for ch in channels:
            policy = store.get_policy(ch.id)
            if policy:
                mem_total += len(store.list_memory(policy.memory_namespace))

        lark_ok = settings.is_configured("Lark")
        # A backend is "ready" only with a real API key, or if the operator explicitly
        # opted into the coding-plan CLI (cli_command alone has a default, so don't count it).
        backend_ok = bool(
            (settings.get("anthropic_api_key") or "").strip()
            or (settings.get("openai_api_key") or "").strip()
            or (settings.get("default_backend") or "").strip() == "cli"
        )
        channel_ok = len(channels) >= 1
        corpus_chunks = store.corpus_count(core.workspace_id)
        checklist = [
            {"label": "Connect Lark", "done": lark_ok,
             "hint": "Add your Lark App ID, Secret, and domain.",
             "link": "/connections"},
            {"label": "Configure a model backend", "done": backend_ok,
             "hint": "Add an API key (Anthropic / OpenAI) or a local coding-agent CLI.",
             "link": "/connections"},
            {"label": "Bind at least one channel", "done": channel_ok,
             "hint": "Point the teammate at a chat where it should live.",
             "link": "/workspace"},
            {"label": "Ingest your Lark knowledge base", "done": corpus_chunks > 0,
             "hint": "Index your existing Lark wiki so the teammate answers from your real docs.",
             "link": "/knowledge"},
        ]
        all_done = all(c["done"] for c in checklist)

        return render(
            request, "dashboard.html", active="dashboard", flash=flash,
            checklist=checklist, all_done=all_done,
            counts={"channels": len(channels), "users": len(users),
                    "memory": mem_total, "knowledge": corpus_chunks},
            enabled_adapters=settings.enabled_adapters(),
            backends=list(core.backends),
            default_backend=(settings.get("default_backend") or "echo"),
            default_model=(settings.get("default_model") or ""),
        )

    # ---------- 2. Connections ----------

    @app.get("/connections", response_class=HTMLResponse)
    def connections(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        groups: dict[str, list[dict]] = {}
        for spec in SETTING_SPECS:
            groups.setdefault(spec.group, []).append({
                "key": spec.key,
                "label": spec.label,
                "secret": spec.secret,
                "help": spec.help,
                "placeholder": spec.placeholder,
                "value": "" if spec.secret else (settings.get(spec.key) or ""),
                "secret_set": bool(spec.secret and (settings.get(spec.key) or "").strip()),
            })
        from agent_tag.lark_cli import LarkCli

        lark_who = None
        try:
            lark_who = LarkCli(config=config).whoami()
        except Exception:  # noqa: BLE001
            lark_who = None
        return render(
            request, "connections.html", active="connections", flash=flash,
            groups=groups, lark_who=lark_who,
            enabled_adapters=settings.enabled_adapters(),
        )

    @app.post("/connections")
    async def connections_save(request: Request):
        if (r := guard(request)) is not None:
            return r
        form = await request.form()
        # str-only values; ignore the implicit form file fields if any.
        values = {k: (v if isinstance(v, str) else "") for k, v in form.items()}
        settings.update_many(values)
        return flash_redirect(
            "/connections",
            "Saved — restart `agent-tag serve` to re-bind chat adapters.",
        )

    # ---------- 3. Workspace ----------

    @app.get("/workspace", response_class=HTMLResponse)
    def workspace_page(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        users = store.list_users(core.org_id)
        channels = store.list_channels()
        chan_rows = []
        for ch in channels:
            policy = store.get_policy(ch.id)
            chan_rows.append({
                "id": ch.id,
                "label": channel_label(ch),
                "platform": ch.platform,
                "external_id": ch.external_id,
                "backend": policy.backend if policy else "—",
                "ambient": bool(policy.ambient_enabled) if policy else False,
                "budget": (policy.token_budget if policy and policy.token_budget else None),
            })
        user_rows = []
        for u in users:
            ids = ", ".join(f"{p}:{x}" for p, x in u.identities.items()) or "—"
            user_rows.append({
                "display_name": u.display_name,
                "role": u.role.value if hasattr(u.role, "value") else str(u.role),
                "identities": ids,
            })
        return render(
            request, "workspace.html", active="workspace", flash=flash,
            workspaces=store.list_workspaces(core.org_id),
            users=user_rows, channels=chan_rows,
            roles=[r.value for r in Role],
        )

    @app.post("/channels/new")
    async def channel_new(request: Request):
        if (r := guard(request)) is not None:
            return r
        form = await request.form()
        platform = (form.get("platform") or "console").strip()
        external_id = (form.get("external_id") or "").strip()
        name = (form.get("name") or "").strip() or external_id
        if not external_id:
            return flash_redirect("/workspace", "A channel id is required.")
        default_backend = settings.get("default_backend") or "echo"
        default_model = settings.get("default_model") or None
        workspace.bind_channel(
            core.workspace_id, platform, external_id, name,
            backend=default_backend, model=default_model,
        )
        return flash_redirect("/workspace", f"Channel “{name}” bound.")

    @app.post("/users/new")
    async def user_new(request: Request):
        if (r := guard(request)) is not None:
            return r
        form = await request.form()
        display_name = (form.get("display_name") or "").strip()
        role_raw = (form.get("role") or "member").strip()
        platform = (form.get("platform") or "").strip()
        external_user_id = (form.get("external_user_id") or "").strip()
        if not display_name:
            return flash_redirect("/workspace", "A display name is required.")
        try:
            role = Role(role_raw)
        except ValueError:
            role = Role.MEMBER
        identities = {platform: external_user_id} if platform and external_user_id else None
        workspace.add_user(core.org_id, display_name, role=role, identities=identities)
        return flash_redirect("/workspace", f"User “{display_name}” added.")

    # ---------- 4. Channel policy editor ----------

    @app.get("/channels/{channel_id}", response_class=HTMLResponse)
    def channel_detail(request: Request, channel_id: str, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        ch = store.get_channel(channel_id)
        policy = store.get_policy(channel_id)
        if ch is None or policy is None:
            return render(request, "not_found.html", active="workspace",
                          what="channel", back="/workspace")
        users = store.list_users(core.org_id)
        return render(
            request, "channel.html", active="workspace", flash=flash,
            channel=ch, policy=policy, label=channel_label(ch),
            backends=list(core.backends),
            all_backends=backends_available(),
            users=users,
        )

    @app.post("/channels/{channel_id}")
    async def channel_save(request: Request, channel_id: str):
        if (r := guard(request)) is not None:
            return r
        policy = store.get_policy(channel_id)
        if policy is None:
            return render(request, "not_found.html", active="workspace",
                          what="channel", back="/workspace")
        form = await request.form()

        def has(name: str) -> bool:
            return name in form

        budget_raw = (form.get("token_budget") or "").strip()
        try:
            token_budget = int(budget_raw) if budget_raw else None
        except ValueError:
            token_budget = policy.token_budget
        try:
            interval = int((form.get("ambient_interval_hours") or "").strip() or policy.ambient_interval_hours)
        except ValueError:
            interval = policy.ambient_interval_hours

        admin_ids = [v for v in form.getlist("admin_user_ids")] if hasattr(form, "getlist") else []

        backend = (form.get("backend") or policy.backend).strip()
        model = (form.get("model") or "").strip() or None

        updated = ChannelPolicy(
            channel_id=policy.channel_id,
            memory_namespace=policy.memory_namespace,
            backend=backend,
            model=model,
            allowed_tools=list(policy.allowed_tools),
            redaction_enabled=has("redaction_enabled"),
            ambient_enabled=has("ambient_enabled"),
            ambient_interval_hours=interval,
            require_mention=has("require_mention"),
            admin_user_ids=admin_ids,
            token_budget=token_budget,
            display_name=(form.get("display_name") or "").strip(),
        )
        store.put_policy(updated)
        return flash_redirect(f"/channels/{channel_id}", "Policy saved.")

    # ---------- 5. Memory ----------

    @app.get("/memory", response_class=HTMLResponse)
    def memory_index(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        channels = store.list_channels()
        rows = []
        for ch in channels:
            policy = store.get_policy(ch.id)
            if policy is None:
                continue
            rows.append({
                "id": ch.id,
                "label": channel_label(ch),
                "platform": ch.platform,
                "namespace": policy.memory_namespace,
                "count": len(store.list_memory(policy.memory_namespace)),
            })
        return render(request, "memory_index.html", active="memory", flash=flash,
                      channels=rows)

    @app.get("/channels/{channel_id}/memory", response_class=HTMLResponse)
    def memory_detail(request: Request, channel_id: str, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        ch = store.get_channel(channel_id)
        policy = store.get_policy(channel_id)
        if ch is None or policy is None:
            return render(request, "not_found.html", active="memory",
                          what="channel", back="/memory")
        items = store.list_memory(policy.memory_namespace)
        return render(request, "memory_detail.html", active="memory", flash=flash,
                      channel=ch, policy=policy, label=channel_label(ch),
                      items=items)

    @app.post("/memory/{item_id}/edit")
    async def memory_edit(request: Request, item_id: str):
        if (r := guard(request)) is not None:
            return r
        form = await request.form()
        content = (form.get("content") or "").strip()
        back = (form.get("back") or "/memory").strip()
        store.update_memory(item_id, content)
        return flash_redirect(back, "Memory updated.")

    @app.post("/memory/{item_id}/delete")
    async def memory_delete(request: Request, item_id: str):
        if (r := guard(request)) is not None:
            return r
        form = await request.form()
        back = (form.get("back") or "/memory").strip()
        store.delete_memory(item_id)
        return flash_redirect(back, "Memory deleted.")

    # ---------- 5b. Knowledge ----------

    @app.get("/knowledge", response_class=HTMLResponse)
    async def knowledge_page(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        import asyncio

        from agent_tag.ingest import list_wiki_spaces
        from agent_tag.lark_cli import LarkCli

        who = None
        try:
            who = LarkCli(config=config).whoami()
        except Exception:  # noqa: BLE001
            who = None

        docs = store.corpus_docs(core.workspace_id)
        total_chunks = store.corpus_count(core.workspace_id)

        # Only attempt to list spaces when the CLI reports an authorized identity;
        # the network call is blocking, so hand it off the event loop.
        spaces: list[dict] = []
        spaces_error = ""
        if who:
            try:
                spaces = await asyncio.to_thread(list_wiki_spaces, LarkCli(config=config))
            except Exception as exc:  # noqa: BLE001
                spaces = []
                spaces_error = str(exc)[:300]
        return render(
            request, "knowledge.html", active="knowledge", flash=flash,
            who=who, docs=docs, total_chunks=total_chunks,
            spaces=spaces, spaces_error=spaces_error,
        )

    @app.post("/knowledge/ingest")
    async def knowledge_ingest(request: Request):
        if (r := guard(request)) is not None:
            return r
        import asyncio

        from agent_tag.ingest import ingest_wiki_space

        form = await request.form()
        space_id = (form.get("space_id") or "").strip()
        name = (form.get("name") or "").strip()
        if not space_id:
            return flash_redirect("/knowledge", "A space id is required.")
        try:
            stats = await asyncio.to_thread(
                ingest_wiki_space, core.store, core.workspace_id, space_id,
                space_name=name, domain=config.lark_domain,
            )
        except Exception as exc:  # noqa: BLE001
            return flash_redirect("/knowledge", f"Ingest failed: {str(exc)[:200]}")
        return flash_redirect(
            "/knowledge",
            "Ingested {docs} docs / {chunks} chunks from {name} ({skipped} skipped).".format(
                docs=stats.get("docs", 0),
                chunks=stats.get("chunks", 0),
                name=stats.get("space_name") or name or space_id,
                skipped=stats.get("skipped", 0),
            ),
        )

    @app.post("/knowledge/clear")
    async def knowledge_clear(request: Request):
        if (r := guard(request)) is not None:
            return r
        core.store.corpus_clear(core.workspace_id)
        return flash_redirect("/knowledge", "Knowledge base cleared.")

    # ---------- 6. Audit ----------

    @app.get("/audit", response_class=HTMLResponse)
    def audit_page(request: Request, channel: str = "", flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        channel_filter = channel.strip() or None
        events = store.list_audit(channel_id=channel_filter, limit=200)
        names = {ch.id: channel_label(ch) for ch in store.list_channels()}
        rows = [{
            "ts": ev.ts,
            "channel": names.get(ev.channel_id, ev.channel_id or "—"),
            "actor": ev.actor,
            "action": ev.action,
            "detail": ev.detail,
            "outcome": ev.outcome,
        } for ev in events]
        return render(request, "audit.html", active="audit", flash=flash,
                      events=rows, channel_filter=channel_filter,
                      channels=store.list_channels(), label=channel_label)

    # ---------- 7. Usage ----------

    @app.get("/usage", response_class=HTMLResponse)
    def usage_page(request: Request, flash: str = ""):
        if (r := guard(request)) is not None:
            return r
        names = {ch.id: channel_label(ch) for ch in store.list_channels()}
        budgets = {}
        for ch in store.list_channels():
            policy = store.get_policy(ch.id)
            budgets[ch.id] = policy.token_budget if policy else None
        rows = []
        for u in store.list_usage():
            budget = budgets.get(u.channel_id)
            pct = None
            if budget:
                pct = min(100, round(u.total / budget * 100)) if budget else 0
            rows.append({
                "channel": names.get(u.channel_id, u.channel_id or "—"),
                "input": u.input_tokens,
                "output": u.output_tokens,
                "total": u.total,
                "budget": budget,
                "pct": pct,
            })
        return render(request, "usage.html", active="usage", flash=flash, rows=rows)

    return app
