"""
Schedules in the interface: list, add, edit, turn on or off, delete, the history of each, and what
was missed while ANCHOR was closed (shown once when it opens).
"""
from __future__ import annotations

from fastapi import Body, HTTPException

from anchor.automations.model import AutomationError, AutomationStore
from anchor.schedules import ScheduleError, ScheduleStore


def add_routes(app, schedules: ScheduleStore, store: AutomationStore, scheduler) -> None:
    def automation_ok(name: str):
        try:
            automation = store.load(name)
        except (AutomationError, FileNotFoundError):
            raise HTTPException(404, "no such automation")
        plan = store.load_plan(name)
        if plan is None or not plan.proven_run:
            raise HTTPException(400, "This automation needs one clean run with you first: run it, with nothing to fix, and then schedule it.")
        return automation

    def view(s):
        history = schedules.history(s.id)
        return {**s.view(), "last": history[0] if history else None}

    @app.get("/api/schedules")
    def all_schedules():
        return [view(s) for s in schedules.all()]

    @app.post("/api/schedules")
    def add(body: dict = Body(...)):
        automation = automation_ok(str(body.get("automation", "")))
        sheet = str(body.get("sheet", "")).strip()
        if automation.parameters and not sheet:
            raise HTTPException(400, "This automation uses values (" + ", ".join(automation.parameters) +
                                "): say which spreadsheet it reads them from.")
        try:
            return view(schedules.add(automation.name, body.get("when") or {}, sheet if automation.parameters else "",
                                      int(body.get("max_rows") or 50)))
        except (ScheduleError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.put("/api/schedules/{id}")
    def edit(id: int, body: dict = Body(...)):
        schedule = schedules.get(id) or _missing()
        automation = automation_ok(schedule.automation)
        sheet = str(body.get("sheet", "")).strip()
        if automation.parameters and not sheet:
            raise HTTPException(400, "Say which spreadsheet it reads the values from.")
        try:
            return view(schedules.update(id, body.get("when") or {}, sheet if automation.parameters else "", int(body.get("max_rows") or 50)))
        except (ScheduleError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.put("/api/schedules/{id}/enabled")
    def enabled(id: int, body: dict = Body(...)):
        schedules.get(id) or _missing()
        return view(schedules.set_enabled(id, bool(body.get("enabled"))))

    @app.delete("/api/schedules/{id}")
    def delete(id: int):
        schedules.get(id) or _missing()
        schedules.delete(id)
        return {"deleted": id}

    @app.get("/api/schedules/{id}/history")
    def history(id: int):
        schedules.get(id) or _missing()
        return schedules.history(id)

    @app.post("/api/schedules/{id}/forget-rows")
    def forget_rows(id: int):
        """The rows this schedule already did are forgotten: the next run does every row of the spreadsheet again."""
        schedules.get(id) or _missing()
        schedules.forget_done(id)
        return {"forgotten": True}

    @app.get("/api/schedules/missed")
    def missed():
        """What was missed while ANCHOR was closed, until the person has seen it."""
        if scheduler is None or scheduler.seen:
            return []
        return scheduler.missed

    @app.post("/api/schedules/missed/seen")
    def seen():
        if scheduler is not None:
            scheduler.seen = True
        return {"seen": True}


def _missing():
    raise HTTPException(404, "no such schedule")
