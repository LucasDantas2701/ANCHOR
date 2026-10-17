"""The API of the local interface, and the app's files."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from anchor import __version__
from anchor.automations.model import AutomationError, AutomationStore

DOCS_URL = "https://github.com/LucasDantas2701/ANCHOR#readme"
STATIC = Path(__file__).parent / "static"
TOKEN_HEADER = "X-Anchor-Token"


def _run_state(status: str) -> str:
    """A run's status, in the three words the interface uses."""
    if status == "success":
        return "checked"
    if status == "cancelled":
        return "stopped"
    return "not_done"


def _run(record: dict) -> dict:
    return {"id": record.get("id", ""), "mode": record.get("mode", ""), "state": _run_state(record.get("status", "")),
            "status": record.get("status", ""), "message": record.get("message", ""),
            "seconds": round(float(record.get("seconds", 0) or 0), 1), "when": record.get("id", "")[:15]}


def _summary(store: AutomationStore, name: str) -> dict:
    automation, plan = store.load(name), store.load_plan(name)
    runs = store.runs(name)
    return {"name": name, "request": automation.request, "url": automation.url, "profile": automation.profile,
            "parameters": automation.parameters, "learned": plan is not None,
            "steps": len(plan.steps) if plan else 0, "proven": bool(plan and plan.proven_run),
            "last_run": _run(runs[-1]) if runs else None}


def create_app(store_root: str | Path = "automations", token: Optional[str] = None,
               static_dir: Path = STATIC, port: Optional[int] = None) -> FastAPI:
    """The app. `token` is the code every API request must carry; `port`, the one it serves on."""
    token = token or secrets.token_urlsafe(24)
    store = AutomationStore(store_root)
    app = FastAPI(title="ANCHOR", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.token = token
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"} if port else None

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Only this computer's own address (a page elsewhere cannot point a name at it), only the
        # app's own origin, and only with the code made at this start.
        host = request.headers.get("host", "")
        if allowed_hosts is not None and host not in allowed_hosts:
            return JSONResponse({"error": "unknown host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and allowed_hosts is not None and origin.split("://", 1)[-1] not in allowed_hosts:
            return JSONResponse({"error": "unknown origin"}, status_code=403)
        if request.url.path.startswith("/api/"):
            given = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(given, token):
                return JSONResponse({"error": "missing or wrong code"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/info")
    def info():
        return {"version": __version__, "docs": DOCS_URL}

    @app.get("/api/automations")
    def automations():
        return [_summary(store, name) for name in store.names()]

    @app.get("/api/automations/{name}")
    def automation(name: str):
        try:
            summary = _summary(store, name)
        except (AutomationError, FileNotFoundError):
            raise HTTPException(404, "no such automation")
        plan = store.load_plan(name)
        summary.update({
            "plan": {"approved": plan.approved, "steps": [{"action": s.action, "description": s.description,
                                                           "value": s.value} for s in plan.steps]} if plan else None,
            "runs": [_run(r) for r in reversed(store.runs(name)[-10:])],
            "recoveries": len(store.recoveries(name)), "notes": len(store.notes(name)),
            "confirmations": len(store.confirmations(name)),
        })
        return summary

    @app.get("/{path:path}")
    def files(path: str):
        # The app's own files; any other path is a page of the app (its router takes it from there).
        target = (static_dir / path).resolve()
        if path and target.is_file() and static_dir.resolve() in target.parents:
            return FileResponse(target)
        index = static_dir / "index.html"
        if not index.is_file():
            raise HTTPException(404, "the interface is not built")
        return FileResponse(index)

    return app
