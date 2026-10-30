"""Schedules: when they run, what is missed while ANCHOR is closed, and the spreadsheet read at run time."""
import time
from datetime import datetime

import pytest

from anchor.automations.model import ApprovedPlan, Automation, AutomationStore
from anchor.planner import Goal, Step
from anchor.schedules import ScheduleError, ScheduleStore, check_when, describe, next_time, row_key
from anchor.schedules.scheduler import Scheduler
from anchor.ui.runs import RunManager

FRIDAY_9 = datetime(2026, 10, 30, 9, 0)


def test_the_next_time_for_each_kind():
    def nxt(when, after=FRIDAY_9):
        return next_time(check_when(when), after)
    assert nxt({"kind": "daily", "time": "08:00"}) == datetime(2026, 10, 31, 8, 0)
    assert nxt({"kind": "weekly", "days": [0, 1, 2, 3, 4], "time": "08:00"}) == datetime(2026, 11, 2, 8, 0)       # Monday
    assert nxt({"kind": "monthly", "day": 31, "time": "07:30"}, datetime(2027, 2, 1)) == datetime(2027, 2, 28, 7, 30)
    every = {"kind": "every", "every": 2, "unit": "hours", "start": "08:00", "window": ["08:00", "18:00"], "days": [0, 1, 2, 3, 4]}
    assert nxt(every) == datetime(2026, 10, 30, 10, 0) and nxt(every, datetime(2026, 10, 30, 18, 1)) == datetime(2026, 11, 2, 8, 0)
    assert nxt({"kind": "once", "at": "2026-10-30T08:00"}) is None                          # already passed
    assert describe(check_when(every)) == "Every 2 hours, from 08:00, between 08:00 and 18:00, on weekdays"


def test_what_a_person_cannot_schedule_is_said_plainly():
    for bad, words in (({"kind": "every", "every": 1, "unit": "minutes"}, "5 minutes"), ({"kind": "weekly", "days": [], "time": "08:00"}, "day"),
                       ({"kind": "every", "every": 1, "unit": "hours", "window": ["18:00", "08:00"]}, "window"), ({"kind": "x"}, "when")):
        with pytest.raises(ScheduleError, match=words):
            check_when(bad)


# --- the scheduler ------------------------------------------------------------------------------------

class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    store = AutomationStore(tmp_path / "automations")
    for name, request in (("report", "baixe o relatório"), ("register", "cadastre {nome} com o CPF {cpf}")):
        store.create(Automation(name=name, request=request, url="https://example.com", profile="ollama-small"))
        plan = ApprovedPlan(steps=[Step("click", "botão Baixar", None)], goals=[Goal("g1", "baixado", True)])
        plan.proven_run = "20261029-0800"
        store.save_plan(name, plan)
    ran = []

    def runner(job):
        ran.append(job.spec)
        rows = job.spec.get("rows")
        if rows:
            return {"state": "checked", "message": "done", "rows": [{"number": i, "state": "checked", "message": "", "values": r}
                                                                       for i, r in enumerate(rows, 1)]}
        return {"state": "checked", "message": "done"}

    runs = RunManager(runner)
    schedules = ScheduleStore(tmp_path / "schedules.db")
    clock = Clock(FRIDAY_9)
    return store, schedules, runs, clock, ran, Scheduler(schedules, store, runs, clock=clock)


def settle(runs):
    for _ in range(50):
        if all(j.state not in ("queued", "running") for j in runs.jobs.values()):
            return
        time.sleep(0.05)


def test_a_due_schedule_runs_with_no_one_present_and_its_result_is_recorded(world):
    store, schedules, runs, clock, ran, scheduler = world
    s = schedules.add("report", {"kind": "daily", "time": "10:00"}, now=clock.now)
    clock.now = datetime(2026, 10, 30, 10, 0, 20)
    scheduler.tick()
    settle(runs)
    assert ran == [{"name": "report", "values": {}, "rows": None, "unattended": True, "schedule": s.id}]
    assert schedules.history(s.id)[0]["state"] == "checked" and schedules.get(s.id).next_run == "2026-10-31T10:00:00"


def test_times_missed_while_closed_are_recorded_once_and_not_run_late(world):
    store, schedules, runs, clock, ran, scheduler = world
    s = schedules.add("report", {"kind": "daily", "time": "08:00"}, now=datetime(2026, 10, 28, 9, 0))
    schedules.alive(datetime(2026, 10, 28, 9, 30))                                  # closed on the 28th, after 09:30
    missed = scheduler.catch_up()                                                    # opened on Friday the 30th, at 09:00
    assert missed == [{"schedule": s.id, "automation": "report", "due": "2026-10-29T08:00", "times": 2}]
    assert schedules.history(s.id)[0]["state"] == "missed" and "closed" in schedules.history(s.id)[0]["message"]
    assert ran == [] and schedules.get(s.id).next_run == "2026-10-31T08:00:00"


def test_an_unproven_automation_or_one_still_running_does_not_start(world, tmp_path):
    store, schedules, runs, clock, ran, scheduler = world
    store.save_plan("report", ApprovedPlan(steps=[Step("click", "x", None)], goals=[Goal("g1", "x", True)]))   # not proven
    s = schedules.add("report", {"kind": "daily", "time": "10:00"}, now=clock.now)
    scheduler.start(schedules.get(s.id), "2026-10-30T10:00:00")
    assert ran == [] and "clean run" in schedules.history(s.id)[0]["message"]
    from anchor.ui.runs import Job
    runs.jobs[99] = Job(id=99, kind="automation", title="register", spec={"name": "register"}, state="running")
    s2 = schedules.add("register", {"kind": "daily", "time": "10:00"}, sheet=str(tmp_path / "x.csv"), now=clock.now)
    scheduler.start(schedules.get(s2.id), "2026-10-30T10:00:00")
    assert schedules.history(s2.id)[0]["state"] == "skipped"


def test_the_spreadsheet_is_checked_at_run_time_and_rows_already_done_are_not_done_again(world, tmp_path):
    store, schedules, runs, clock, ran, scheduler = world
    sheet = tmp_path / "novos.csv"
    sheet.write_text("nome;cpf\nAna;1\nBia;\n", encoding="utf-8")
    s = schedules.add("register", {"kind": "daily", "time": "18:00"}, sheet=str(sheet), max_rows=2, now=clock.now)
    scheduler.start(schedules.get(s.id), "d1")
    settle(runs)
    assert ran[-1]["rows"] == [{"nome": "Ana", "cpf": "1"}]                         # Bia's empty CPF: skipped
    assert "empty value" in schedules.history(s.id)[0]["message"] and row_key({"nome": "Ana", "cpf": "1"}) in schedules.done(s.id)
    sheet.write_text("nome;cpf\nAna;1\nCaio;2\n", encoding="utf-8")                  # the next day, one new row
    scheduler.start(schedules.get(s.id), "d2")
    settle(runs)
    assert ran[-1]["rows"] == [{"nome": "Caio", "cpf": "2"}]                        # Ana was done before
    scheduler.start(schedules.get(s.id), "d3")
    assert schedules.history(s.id)[0]["state"] == "nothing" and len(ran) == 2       # nothing new: nothing runs
    sheet.write_text("nome;cpf\nD;3\nE;4\nF;5\n", encoding="utf-8")                  # more than the limit
    scheduler.start(schedules.get(s.id), "d4")
    assert schedules.history(s.id)[0]["state"] == "not_done" and "limit of 2" in schedules.history(s.id)[0]["message"]
    sheet.write_text("nome\nG\n", encoding="utf-8")                                  # a column is gone
    scheduler.start(schedules.get(s.id), "d5")
    assert "no column for: cpf" in schedules.history(s.id)[0]["message"] and len(ran) == 2


def test_the_interface_refuses_an_unproven_automation_and_values_without_a_spreadsheet(world, tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.server import create_app
    from tests.ui.test_runs import HEADERS, PORT
    store, *_ = world
    app = create_app(store.root, token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""}, headless=True,
                     schedules_path=tmp_path / "s.db")
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    when = {"kind": "daily", "time": "08:00"}
    assert c.post("/api/schedules", json={"automation": "register", "when": when}, headers=HEADERS).status_code == 400
    ok = c.post("/api/schedules", json={"automation": "report", "when": when}, headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["words"] == "Every day at 08:00"
    assert c.put(f"/api/schedules/{ok.json()['id']}/enabled", json={"enabled": False}, headers=HEADERS).json()["next_run"] is None
    app.state.scheduler.missed = [{"schedule": 1, "automation": "report", "due": "2026-10-30T08:00", "times": 1}]
    assert len(c.get("/api/schedules/missed", headers=HEADERS).json()) == 1
    c.post("/api/schedules/missed/seen", headers=HEADERS)
    assert c.get("/api/schedules/missed", headers=HEADERS).json() == []                # shown once
