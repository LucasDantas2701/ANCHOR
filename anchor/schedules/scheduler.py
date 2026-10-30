"""
The scheduler: inside ANCHOR, every 30 seconds, it puts the schedules that are due in the queue, as
runs with no one present. It only works while ANCHOR is open: when it opens, the times it missed
while it was closed are recorded as missed (not run late), and the interface shows them once.

A schedule's automation must be proven (one clean run with someone present). With values, it reads
its spreadsheet at run time, as it is then, and checks it first: a missing column or an unreadable
file runs nothing; more rows than the schedule's limit runs nothing; rows with an empty value are
skipped; and rows this schedule already did are not done again (by their content).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from anchor.automations.model import AutomationError, AutomationStore
from anchor.automations.params import ParameterError, check_rows, rows_from_file

from . import Schedule, ScheduleStore, next_time, row_key

TICK = 30                                # seconds between checks
ACTIVE = ("queued", "running", "waiting")


class Scheduler:
    def __init__(self, schedules: ScheduleStore, automations: AutomationStore, runs, clock=datetime.now):
        self.schedules, self.automations, self.runs, self.clock = schedules, automations, runs, clock
        self.opened = clock()
        self.missed: list[dict] = []     # what was missed while ANCHOR was closed, shown once when it opens
        self.seen = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ opening: the times missed while closed
    def catch_up(self) -> list[dict]:
        """Records, as missed, every time a schedule was due while ANCHOR was closed; nothing runs late."""
        now, last = self.clock(), self.schedules.last_alive()
        missed = []
        for schedule in self.schedules.all():
            if not schedule.enabled or not schedule.next_run:
                continue
            due = datetime.fromisoformat(schedule.next_run)
            count, first = 0, due
            while due is not None and due <= now:
                if last is None or due > last - timedelta(seconds=TICK):   # it was due after ANCHOR closed
                    count += 1
                due = next_time(schedule.when, due)
            if count:
                self.schedules.record(schedule.id, first.isoformat(timespec="seconds"), "missed",
                                      "ANCHOR was closed at this time" + (f" ({count} times)" if count > 1 else ""))
                missed.append({"schedule": schedule.id, "automation": schedule.automation, "due": first.isoformat(timespec="minutes"),
                               "times": count})
            self.schedules.set_next(schedule.id, next_time(schedule.when, now))
        self.schedules.alive(now)
        self.missed = missed
        return missed

    # ------------------------------------------------------------------ every tick
    def tick(self) -> None:
        now = self.clock()
        for schedule in self.schedules.all():
            if schedule.enabled and schedule.next_run and datetime.fromisoformat(schedule.next_run) <= now:
                due = schedule.next_run
                self.schedules.set_next(schedule.id, next_time(schedule.when, now))
                self.start(schedule, due)
        self.schedules.alive(now)

    def start(self, schedule: Schedule, due: str) -> Optional[int]:
        """Puts one due time of a schedule in the queue, after its checks; returns the history entry."""
        name = schedule.automation
        try:
            automation = self.automations.load(name)
        except (AutomationError, FileNotFoundError):
            self.schedules.record(schedule.id, due, "error", "The automation no longer exists.")
            return None
        plan = self.automations.load_plan(name)
        if plan is None or not plan.proven_run:
            self.schedules.record(schedule.id, due, "error", "The automation needs one clean run with you first.")
            return None
        if any(j.state in ACTIVE and j.kind in ("automation", "login") and j.spec.get("name") == name for j in self.runs.jobs.values()):
            self.schedules.record(schedule.id, due, "skipped", "Its previous run was still going.")
            return None
        rows, note = None, ""
        if automation.parameters:
            rows, note, problem = self.rows(schedule, automation.parameters)
            if problem:
                self.schedules.record(schedule.id, due, "not_done", problem)
                return None
            if not rows:
                self.schedules.record(schedule.id, due, "nothing", "No new rows in the spreadsheet." + note)
                return None
        entry = self.schedules.record(schedule.id, due, "running", note.strip())
        job = self.runs.submit("automation", name, {"name": name, "values": {}, "rows": rows, "unattended": True,
                                                    "schedule": schedule.id})
        job.on_end = lambda j: self.ended(schedule.id, entry, j, rows, note)
        return entry

    def rows(self, schedule: Schedule, parameters: list[str]) -> tuple[Optional[list], str, str]:
        """The rows to run now: (rows, a note, a problem that stops the run)."""
        path = Path(schedule.sheet)
        if not schedule.sheet or not path.is_file():
            return None, "", f"The spreadsheet {schedule.sheet or '(none)'} was not found."
        try:
            rows = rows_from_file(path.read_bytes(), path.name)
        except (ParameterError, OSError) as exc:
            return None, "", f"The spreadsheet could not be read: {exc}"
        checked = check_rows(parameters, rows)
        if checked["missing"]:
            return None, "", "The spreadsheet has no column for: " + ", ".join(checked["missing"]) + "."
        blank = set(checked["blank_rows"])
        done = self.schedules.done(schedule.id)
        fresh = [{p: r.get(p, "") for p in parameters} for n, r in enumerate(rows, 1) if n not in blank]
        fresh = [r for r in fresh if row_key(r) not in done]
        note = f" {len(blank)} row(s) with an empty value were skipped." if blank else ""
        if len(fresh) > schedule.max_rows:
            return None, "", f"{len(fresh)} new rows, more than this schedule's limit of {schedule.max_rows}: nothing was run."
        return fresh, note, ""

    def ended(self, schedule: int, entry: int, job, rows: Optional[list], note: str = "") -> None:
        result = job.result or {}
        if rows is not None and result.get("rows"):
            done = [row_key(r["values"]) for r in result["rows"] if r.get("state") == "checked"]
            self.schedules.mark_done(schedule, done)
        self.schedules.finish(entry, result.get("state", "not_done"), (result.get("message", "") + note).strip())

    # ------------------------------------------------------------------ the loop
    def run_forever(self) -> None:
        self.catch_up()
        while not self._stop.wait(TICK):
            try:
                self.tick()
            except Exception:                    # a bad tick must not stop the schedules
                pass

    def start_thread(self) -> None:
        self._thread = threading.Thread(target=self.run_forever, name="anchor-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
