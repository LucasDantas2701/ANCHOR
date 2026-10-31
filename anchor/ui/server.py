"""The API of the local interface, and the app's files."""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from anchor import __version__
from anchor.agent.__main__ import to_url
from anchor.agent.login import request_has_password
from anchor.automations.model import ApprovedPlan, Automation, AutomationError, AutomationStore
from anchor.engine.memory.choices import ChoiceMemory
from anchor.i18n import set_language, t
from anchor.planner import Goal, Step
from anchor.planner.config import ConfigError, load_profiles

from .desktop import add_routes as add_desktop_routes
from .logins import add_routes as add_login_routes
from .manage import add_routes as add_manage_routes
from .runs import RunManager, Runner
from .schedules import add_routes as add_schedule_routes

DOCS_URL = "https://lucasdantas2701.github.io/ANCHOR/"     # the documentation site (built from the repository)
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


def _profiles(setup=None) -> list[dict]:
    """The model profiles that can be used (a profile still waiting for its model name is left out); in the
    desktop program, each says whether its model is downloaded."""
    try:
        profiles = load_profiles()
    except ConfigError:
        return []
    names = {"ollama-small": "Small · Qwen 3.5 4B", "ollama-medium": "Medium · Qwen 3.5 9B"}
    downloaded = setup.downloaded() if setup is not None else {}
    return [{"name": n, "label": names.get(n, n), **({"downloaded": downloaded[n]} if n in downloaded else {})}
            for n, p in profiles.items() if not str(p.model).startswith("PUT_")]


def create_app(store_root: str | Path = "automations", token: Optional[str] = None,
               static_dir: Path = STATIC, port: Optional[int] = None, runner: Optional[Runner] = None,
               headless: bool = False, request_memory: str | Path = "memory/agent.json",
               vault=None, schedules_path: Optional[str | Path] = None, run_schedules: bool = False,
               desktop=None, setup=None) -> FastAPI:
    """
    The app. `token` is the code every API request must carry; `port`, the one it serves on;
    `runner` does the runs (default: the real browser and model, with a window unless `headless`).
    """
    token = token or secrets.token_urlsafe(24)
    store = AutomationStore(store_root)
    if vault is None:                         # saved logins: passwords in the system's credential store
        from anchor.vault import LoginVault
        vault = LoginVault("memory/logins.json")
    set_language("en")                       # the interface is in English, and so is what runs say
    if runner is None:
        from .execute import Executor
        runner = Executor(store, headless=headless, vault=vault)
    runs = RunManager(runner)
    app = FastAPI(title="ANCHOR", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runs = runs
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
            "choices": len(ChoiceMemory(store.memory_path(name)).entries),
        })
        return summary

    @app.get("/api/profiles")
    def profiles():
        return _profiles(setup)

    def job_or_404(run_id: int):
        job = runs.jobs.get(run_id)
        if job is None:
            raise HTTPException(404, "no such run")
        return job

    @app.post("/api/runs")
    def start(body: dict = Body(...)):
        kind = body.get("kind")
        if kind == "automation":
            name = str(body.get("name", ""))
            try:
                automation = store.load(name)
            except (AutomationError, FileNotFoundError):
                raise HTTPException(404, "no such automation")
            values = {str(k): str(v) for k, v in (body.get("values") or {}).items()}
            rows = body.get("rows")
            if rows is not None:                        # a spreadsheet: one run of the automation per row
                from anchor.automations.params import MAX_ROWS, check_rows
                if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
                    raise HTTPException(400, "The spreadsheet has no rows.")
                rows = [{str(k): str(v) for k, v in r.items()} for r in rows]
                checked = check_rows(automation.parameters, rows)
                if checked["too_many"]:
                    raise HTTPException(400, f"A spreadsheet run has at most {MAX_ROWS} rows.")
                if checked["missing"]:
                    raise HTTPException(400, "The spreadsheet has no column for: " + ", ".join(checked["missing"]) + ".")
                if checked["blank_rows"]:
                    raise HTTPException(400, "These rows have an empty value: " + ", ".join(map(str, checked["blank_rows"][:10])) + ".")
                values = {}
            else:
                missing = [p for p in automation.parameters if not values.get(p, "").strip()]
                if missing:
                    raise HTTPException(400, "Fill in: " + ", ".join(missing) + ".")
            job = runs.submit("automation", name, {"name": name, "values": values, "rows": rows, "relearn": bool(body.get("relearn")),
                                                   "fresh_browser": bool(body.get("fresh_browser")),
                                                   "show_browser": bool(body.get("show_browser", False)),
                                                   "screenshot": bool(body.get("screenshot"))})
        elif kind in ("request", "plan"):
            request, url, profile = (str(body.get(k, "")).strip() for k in ("request", "url", "profile"))
            if not request or not url:
                raise HTTPException(400, "Write the request and the page's address.")
            if request_has_password(request):
                raise HTTPException(400, t("end.password_in_request"))
            if profile not in {p["name"] for p in _profiles()}:
                raise HTTPException(400, "Choose a model.")
            url = to_url(url)
            if "://" not in url:                 # "crm.example.com" is a website, as a person writes it
                url = "https://" + url
            job = runs.submit(kind, request, {"request": request, "url": url, "profile": profile,
                                              "show_browser": bool(body.get("show_browser", False)),
                                              "screenshot": bool(body.get("screenshot"))})
        else:
            raise HTTPException(400, "unknown kind of run")
        return {"id": job.id, "position": runs.position(job)}

    @app.get("/api/runs")
    def all_runs():
        return runs.list()

    @app.get("/api/runs/{run_id}")
    def one_run(run_id: int, after: int = 0):
        job = job_or_404(run_id)
        return {**job.view(after), "position": runs.position(job)}

    @app.post("/api/runs/{run_id}/answer")
    def answer(run_id: int, body: dict = Body(...)):
        job = job_or_404(run_id)
        if not job.give(int(body.get("number", 0)), dict(body.get("answer") or {})):
            raise HTTPException(409, "that question is no longer open")
        return {"ok": True}

    @app.get("/api/runs/{run_id}/frame")
    def frame(run_id: int, after: int = 0):
        """The live view's latest image (asking for it is what keeps the live view on)."""
        job = job_or_404(run_id)
        job.watched = time.time()
        latest = job.frame
        if latest is None or latest[0] <= after:
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        return Response(latest[1], media_type="image/jpeg",
                        headers={"X-Frame": str(latest[0]), "Cache-Control": "no-store"})

    @app.get("/api/runs/{run_id}/outputs/{number}")
    def output_file(run_id: int, number: int, row: int = 0):
        """A file a run brought back (a table's CSV, a download, a screenshot): only one listed in its outputs."""
        job = job_or_404(run_id)
        result = job.result or {}
        outputs = result.get("outputs") or []
        if row:
            rows = [r for r in result.get("rows") or [] if r.get("number") == row]
            outputs = rows[0].get("outputs", []) if rows else []
        if not 0 <= number < len(outputs) or not outputs[number].get("path"):
            raise HTTPException(404, "no such output")
        path = Path(outputs[number]["path"])
        if not path.is_file():
            raise HTTPException(404, "the file is no longer there")
        return FileResponse(path, filename=path.name)

    @app.get("/api/runs/{run_id}/details")
    def details(run_id: int):
        """What the model read and answered at each planning, for diagnosis; a file saved on this computer."""
        job = job_or_404(run_id)
        body = {"anchor": __version__, "run": job.id, "kind": job.kind, "title": job.title, "state": job.state,
                "about": job.about, "result": job.result, "events": job.events, "plannings": job.details}
        return Response(json.dumps(body, ensure_ascii=False, indent=1, default=str), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="anchor-run-{job.id}.json"'})

    @app.post("/api/runs/{run_id}/input")
    def give_input(run_id: int, body: dict = Body(...)):
        """A click or keys from the live view: taken only while a login or a pointing waits for them."""
        job = job_or_404(run_id)
        if not job.takes_input():
            raise HTTPException(409, "the browser takes your clicks and keys only when ANCHOR asks for them")
        if len(job.inputs) < 200:
            job.inputs.append({k: body.get(k) for k in ("type", "x", "y", "dy", "text", "key")})
        return {"ok": True}

    def create(name: str, request: str, url: str, profile: str):
        """A new automation, the way the command line creates one (the store checks the name)."""
        name, request, url = name.strip(), request.strip(), url.strip()
        if not request or not url:
            raise HTTPException(400, "Write the request and the page's address.")
        if request_has_password(request):
            raise HTTPException(400, t("end.password_in_request"))
        if profile not in {p["name"] for p in _profiles()}:
            raise HTTPException(400, "Choose a model.")
        url = to_url(url)
        if "://" not in url:
            url = "https://" + url
        try:
            store.create(Automation(name=name, request=request, url=url, profile=profile))
        except AutomationError as exc:
            raise HTTPException(400, str(exc))
        return name

    @app.post("/api/automations")
    def new_automation(body: dict = Body(...)):
        name = create(*(str(body.get(k, "")) for k in ("name", "request", "url", "profile")))
        return _summary(store, name)

    @app.post("/api/runs/{run_id}/tab")
    def tab(run_id: int, body: dict):
        """The tab the person wants to see on the live view (and to click on during a login); null: ANCHOR's."""
        job = job_or_404(run_id)
        index = body.get("index")
        job.viewing = int(index) if isinstance(index, int) and index >= 0 else None
        return {"viewing": job.viewing}

    @app.post("/api/runs/{run_id}/save")
    def save_as_automation(run_id: int, body: dict = Body(...)):
        """A checked request becomes an automation with the plan of that very run (no run again)."""
        job = job_or_404(run_id)
        if not job.view()["can_save"]:
            raise HTTPException(409, "Only a request that was done and checked can become an automation.")
        spec = job.spec
        name = create(str(body.get("name", "")), spec["request"], spec["url"], spec["profile"])
        learned = job.learned
        # Not proven: before it may run with no one present, it needs one clean run with someone there.
        store.save_plan(name, ApprovedPlan(steps=[Step(**s) for s in learned["steps"]],
                                           goals=[Goal(**g) for g in learned["goals"]],
                                           source_run="", language=learned.get("language") or "pt"))
        return _summary(store, name)

    @app.post("/api/automations/{name}/login")
    def log_in(name: str):
        """Log in to the automation's site once; the session stays in its browser profile."""
        try:
            store.load(name)
        except (AutomationError, FileNotFoundError):
            raise HTTPException(404, "no such automation")
        job = runs.submit("login", name, {"name": name})
        return {"id": job.id, "position": runs.position(job)}

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: int):
        runs.stop(job_or_404(run_id))
        return {"ok": True}

    # Looking after a saved automation: fixes, notes, decisions, choices, edit, delete (anchor/ui/manage.py).
    add_manage_routes(app, store, runs, request_memory)
    # Saved logins (Settings): passwords go to the system's credential store and are never answered.
    app.state.vault = vault
    add_login_routes(app, vault)
    # Schedules: kept in a local SQLite file; they run only while ANCHOR is open (run_schedules: the real app).
    from anchor.schedules import ScheduleStore
    from anchor.schedules.scheduler import Scheduler
    if schedules_path is None:                 # the real app keeps them in memory/; a test app, in a temporary folder
        import tempfile
        schedules_path = "memory/schedules.db" if run_schedules else Path(tempfile.mkdtemp(prefix="anchor-")) / "schedules.db"
    schedules = ScheduleStore(schedules_path)
    scheduler = Scheduler(schedules, store, runs)
    app.state.schedules, app.state.scheduler = schedules, scheduler
    if run_schedules:
        scheduler.start_thread()
    add_schedule_routes(app, schedules, store, scheduler)
    # The desktop program (anchor/desktop): first opening's checks, Start with Windows, the window.
    add_desktop_routes(app, desktop, setup)

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
