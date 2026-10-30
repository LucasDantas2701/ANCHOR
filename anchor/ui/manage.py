"""
Looking after a saved automation from the interface: its fixes (and undoing one), its notes for the
planner, its decisions on sensitive actions, its remembered choices, editing it and deleting it.
Each route uses the same code as the command line (anchor.automations), so both behave alike.

An automation that is waiting or running in the queue is not changed: undoing, editing and deleting
answer 409 until its run ends.
"""
from __future__ import annotations

from fastapi import Body, HTTPException

from anchor.automations.model import AutomationError, AutomationStore
from anchor.automations.runner import undo_recovery
from anchor.engine.memory.choices import ChoiceMemory

ACTIVE = ("queued", "running", "waiting")


def _step(step: dict | None) -> dict | None:
    if not step:
        return None
    return {"action": step.get("action"), "description": step.get("description"), "value": step.get("value")}


def fix_view(record: dict) -> dict:
    """A recovery as the interface shows it: what failed and what replaced it, or the element you chose."""
    view = {"number": record["number"], "date": record["date"], "undone": bool(record.get("undone")),
            "method": record.get("method", "replan")}
    if view["method"] == "replan":
        view.update(failed=_step(record.get("failed_step")), reason=record.get("reason", ""),
                    replaced_by=[_step(s) for s in record.get("replaced_by", [])],
                    effect_confirmed=bool(record.get("effect_confirmed")))
    else:
        view.update(step=_step(record.get("step")))
    return view


def add_routes(app, store: AutomationStore, runs) -> None:
    def loaded(name: str):
        try:
            return store.load(name)
        except (AutomationError, FileNotFoundError):
            raise HTTPException(404, "no such automation")

    def idle(name: str) -> None:
        for job in runs.jobs.values():
            if job.state in ACTIVE and job.kind in ("automation", "login") and job.spec.get("name") == name:
                raise HTTPException(409, "this automation is in the queue or running; wait until its run ends")

    # ------------------------------------------------------------------ fixes
    @app.get("/api/automations/{name}/fixes")
    def fixes(name: str):
        loaded(name)
        return [fix_view(r) for r in reversed(store.recoveries(name))]

    @app.post("/api/automations/{name}/fixes/{number}/undo")
    def undo(name: str, number: int):
        loaded(name)
        idle(name)
        try:
            record = undo_recovery(store, name, number, memory=ChoiceMemory(store.memory_path(name)))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return fix_view({**record, "undone": True})

    # ------------------------------------------------------------------ notes
    @app.get("/api/automations/{name}/notes")
    def notes(name: str):
        loaded(name)
        sent = store.NOTES_SENT
        items = store.notes(name)
        return [{**n, "sent": i >= len(items) - sent} for i, n in enumerate(items)][::-1]

    @app.post("/api/automations/{name}/notes")
    def add_note(name: str, body: dict = Body(...)):
        loaded(name)
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "write the note")
        if len(text) > 500:
            raise HTTPException(400, "a note has at most 500 characters")
        return store.add_note(name, text, run=str(body.get("run", "")))

    @app.put("/api/automations/{name}/notes/{number}")
    def edit_note(name: str, number: int, body: dict = Body(...)):
        loaded(name)
        text = str(body.get("text", "")).strip()
        if not text or len(text) > 500:
            raise HTTPException(400, "a note has 1 to 500 characters")
        if not store.update_note(name, number, text):
            raise HTTPException(404, "no such note")
        return {"number": number, "text": text}

    @app.delete("/api/automations/{name}/notes/{number}")
    def remove_note(name: str, number: int):
        loaded(name)
        if not store.remove_note(name, number):
            raise HTTPException(404, "no such note")
        return {"removed": number}

    # ------------------------------------------------------------------ decisions on sensitive actions
    @app.get("/api/automations/{name}/decisions")
    def decisions(name: str):
        loaded(name)
        return [{"number": d["number"], "date": d["date"], "action": d.get("action"), "element": d.get("element"),
                 "category": d.get("category"), "decision": d.get("decision")} for d in reversed(store.confirmations(name))]

    @app.delete("/api/automations/{name}/decisions/{number}")
    def forget_decision(name: str, number: int):
        loaded(name)
        if not store.forget_confirmation(name, number):
            raise HTTPException(404, "no such decision")
        return {"forgotten": number}

    # ------------------------------------------------------------------ remembered choices
    @app.get("/api/automations/{name}/choices")
    def choices(name: str):
        loaded(name)
        memory = ChoiceMemory(store.memory_path(name))
        return [{"key": key, "action": e.action, "description": e.description, "url": e.url,
                 "element": (e.signature or {}).get("text") or (e.signature or {}).get("label") or "",
                 "uses": e.uses, "last_used": e.last_used} for key, e in memory.ordered()]

    @app.delete("/api/automations/{name}/choices")
    def forget_choice(name: str, key: str):
        loaded(name)
        if not ChoiceMemory(store.memory_path(name)).forget_key(key):
            raise HTTPException(404, "no such choice")
        return {"forgotten": key}

    # ------------------------------------------------------------------ edit and delete
    @app.put("/api/automations/{name}")
    def edit(name: str, body: dict = Body(...)):
        loaded(name)
        idle(name)
        try:
            automation, forgot = store.update(name, str(body.get("request", "")), str(body.get("url", "")),
                                              str(body.get("profile", "")))
        except AutomationError as exc:
            raise HTTPException(400, str(exc))
        return {"name": name, "relearn": forgot, "parameters": automation.parameters}

    @app.delete("/api/automations/{name}")
    def delete(name: str, confirm: str = ""):
        loaded(name)
        if confirm != name:
            raise HTTPException(400, "type the automation's name to delete it")
        idle(name)
        try:
            store.delete(name)
        except AutomationError as exc:
            raise HTTPException(400, str(exc))
        return {"deleted": name}
