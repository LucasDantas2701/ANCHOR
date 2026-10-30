"""
Schedules: an automation run by itself at set times, while ANCHOR is open.

Kept in a local SQLite file (memory/schedules.db): the schedules, the history of each one (done,
not done, skipped, missed because ANCHOR was closed) and the spreadsheet rows each schedule already
did, so the next time it runs only the new ones. The time is this computer's local time.

When (a schedule's "when", as JSON):
    {"kind": "once",    "at": "2026-11-03T08:00"}
    {"kind": "daily",   "time": "08:00"}
    {"kind": "weekly",  "days": [0, 2, 4], "time": "08:00"}          Monday = 0
    {"kind": "monthly", "day": 31, "time": "08:00"}                  the month's last day if it is shorter
    {"kind": "every",   "every": 2, "unit": "hours", "start": "08:00",
                        "window": ["08:00", "18:00"] or null, "days": [0, 1, 2, 3, 4] or null}
"""
from __future__ import annotations

import calendar
import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

KINDS = ("once", "daily", "weekly", "monthly", "every")
UNITS = {"minutes": 60, "hours": 3600, "days": 86400}
MIN_EVERY = timedelta(minutes=5)          # nothing more often than every 5 minutes
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class ScheduleError(ValueError):
    pass


def _time(text: str) -> time:
    try:
        hours, minutes = (int(x) for x in str(text).split(":")[:2])
        return time(hours, minutes)
    except Exception:
        raise ScheduleError(f"a time like 08:00, not {text!r}")


def _days(days) -> list[int]:
    if not isinstance(days, list) or not days or not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
        raise ScheduleError("choose at least one day of the week")
    return sorted(set(days))


def check_when(when: dict) -> dict:
    """The schedule's "when", checked and normalized (raises ScheduleError with a sentence a person reads)."""
    if not isinstance(when, dict) or when.get("kind") not in KINDS:
        raise ScheduleError("choose when it runs")
    kind = when["kind"]
    if kind == "once":
        try:
            at = datetime.fromisoformat(str(when.get("at")))
        except ValueError:
            raise ScheduleError("choose the date and time")
        return {"kind": kind, "at": at.strftime("%Y-%m-%dT%H:%M")}
    if kind == "daily":
        return {"kind": kind, "time": _time(when.get("time")).strftime("%H:%M")}
    if kind == "weekly":
        return {"kind": kind, "days": _days(when.get("days")), "time": _time(when.get("time")).strftime("%H:%M")}
    if kind == "monthly":
        day = when.get("day")
        if not isinstance(day, int) or not 1 <= day <= 31:
            raise ScheduleError("choose a day of the month from 1 to 31")
        return {"kind": kind, "day": day, "time": _time(when.get("time")).strftime("%H:%M")}
    every, unit = when.get("every"), when.get("unit")
    if not isinstance(every, int) or every < 1 or unit not in UNITS:
        raise ScheduleError("say every how many minutes, hours or days")
    if timedelta(seconds=every * UNITS[unit]) < MIN_EVERY:
        raise ScheduleError("at most every 5 minutes")
    window = when.get("window")
    if window:
        start, end = _time(window[0]), _time(window[1])
        if not start < end:
            raise ScheduleError("the window's start must come before its end")
        window = [start.strftime("%H:%M"), end.strftime("%H:%M")]
    days = _days(when["days"]) if when.get("days") else None
    return {"kind": kind, "every": every, "unit": unit, "start": _time(when.get("start", "00:00")).strftime("%H:%M"),
            "window": window or None, "days": days}


def next_time(when: dict, after: datetime) -> Optional[datetime]:
    """The first time strictly after `after` at which the schedule runs (None: never again)."""
    kind = when["kind"]
    if kind == "once":
        at = datetime.fromisoformat(when["at"])
        return at if at > after else None
    if kind in ("daily", "weekly", "monthly"):
        hour = _time(when["time"])
        day = after.date()
        for _ in range(400):                                   # a year and a bit always finds the next one
            if _runs_on(when, day):
                at = datetime.combine(_month_day(when, day), hour) if kind == "monthly" else datetime.combine(day, hour)
                if at > after and at.date() == day:
                    return at
            day += timedelta(days=1)
        return None
    step = timedelta(seconds=when["every"] * UNITS[when["unit"]])
    start = datetime.combine(after.date() - timedelta(days=1), _time(when["start"]))
    at = start
    if at <= after:
        at += step * ((after - at) // step + 1)
    for _ in range(100000):
        if _fits(when, at):
            return at
        at += step
    return None


def _runs_on(when: dict, day: date) -> bool:
    if when["kind"] == "daily":
        return True
    if when["kind"] == "weekly":
        return day.weekday() in when["days"]
    return day.day == min(when["day"], calendar.monthrange(day.year, day.month)[1])


def _month_day(when: dict, day: date) -> date:
    return day


def _fits(when: dict, at: datetime) -> bool:
    if when.get("days") and at.weekday() not in when["days"]:
        return False
    if when.get("window"):
        start, end = _time(when["window"][0]), _time(when["window"][1])
        if not start <= at.time() <= end:
            return False
    return True


def describe(when: dict) -> str:
    """The schedule in words, for the list: "Every weekday at 08:00"."""
    kind = when["kind"]
    if kind == "once":
        return "Once, on " + datetime.fromisoformat(when["at"]).strftime("%d %b %Y at %H:%M")
    if kind == "daily":
        return f"Every day at {when['time']}"
    if kind == "weekly":
        return f"Every {_day_list(when['days'])} at {when['time']}"
    if kind == "monthly":
        last = " (or the month's last day)" if when["day"] > 28 else ""
        return f"Every month on day {when['day']}{last} at {when['time']}"
    unit = when["unit"] if when["every"] > 1 else when["unit"].rstrip("s")
    text = f"Every {when['every']} {unit}" if when["every"] > 1 else f"Every {unit}"
    text += f", from {when['start']}"
    if when.get("window"):
        text += f", between {when['window'][0]} and {when['window'][1]}"
    if when.get("days"):
        days = when["days"]
        text += ", on weekdays" if days == [0, 1, 2, 3, 4] else ", on weekends" if days == [5, 6] else f", on {_day_list(days)}"
    return text


def _day_list(days: list[int]) -> str:
    if days == [0, 1, 2, 3, 4]:
        return "weekday"
    if days == [5, 6]:
        return "weekend day"
    names = [DAY_NAMES[d] for d in days]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]


def row_key(values: dict) -> str:
    """A spreadsheet row's identity, by its content: the same person with the same data is the same row."""
    return hashlib.sha256(json.dumps(sorted(values.items()), ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass
class Schedule:
    id: int
    automation: str
    when: dict
    sheet: str = ""                      # the spreadsheet read at run time (automations with values)
    max_rows: int = 50                   # more rows than this: it does not run, and says so
    enabled: bool = True
    created: str = ""
    next_run: Optional[str] = None

    def view(self) -> dict:
        return {"id": self.id, "automation": self.automation, "when": self.when, "words": describe(self.when),
                "sheet": self.sheet, "max_rows": self.max_rows, "enabled": self.enabled, "created": self.created,
                "next_run": self.next_run}


SCHEMA = """
create table if not exists schedules (id integer primary key, automation text not null, spec text not null, sheet text not null default '',
  max_rows integer not null default 50, enabled integer not null default 1, created text not null, next_run text);
create table if not exists history (id integer primary key, schedule integer not null, due text not null, at text not null,
  state text not null, message text not null default '', run integer);
create table if not exists done_rows (schedule integer not null, row text not null, at text not null, primary key (schedule, row));
create table if not exists meta (key text primary key, value text);
"""


class ScheduleStore:
    def __init__(self, path: str | Path = "memory/schedules.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------------ schedules
    def _schedule(self, row) -> Schedule:
        return Schedule(row["id"], row["automation"], json.loads(row["spec"]), row["sheet"], row["max_rows"],
                        bool(row["enabled"]), row["created"], row["next_run"])

    def all(self) -> list[Schedule]:
        with self.lock, self._db() as db:
            return [self._schedule(r) for r in db.execute("select * from schedules order by id")]

    def get(self, id: int) -> Optional[Schedule]:
        with self.lock, self._db() as db:
            row = db.execute("select * from schedules where id = ?", (id,)).fetchone()
        return self._schedule(row) if row else None

    def add(self, automation: str, when: dict, sheet: str = "", max_rows: int = 50, now: Optional[datetime] = None) -> Schedule:
        when = check_when(when)
        if not 1 <= int(max_rows) <= 500:
            raise ScheduleError("the most rows per run is from 1 to 500")
        now = now or datetime.now()
        upcoming = next_time(when, now)
        if upcoming is None:
            raise ScheduleError("that time has already passed")
        with self.lock, self._db() as db:
            cur = db.execute("insert into schedules (automation, spec, sheet, max_rows, enabled, created, next_run) values (?, ?, ?, ?, 1, ?, ?)",
                             (automation, json.dumps(when), sheet.strip(), int(max_rows), now.isoformat(timespec="seconds"),
                              upcoming.isoformat(timespec="seconds")))
            id = cur.lastrowid
        return self.get(id)

    def update(self, id: int, when: dict, sheet: str, max_rows: int, now: Optional[datetime] = None) -> Schedule:
        when = check_when(when)
        if not 1 <= int(max_rows) <= 500:
            raise ScheduleError("the most rows per run is from 1 to 500")
        upcoming = next_time(when, now or datetime.now())
        with self.lock, self._db() as db:
            db.execute("update schedules set spec = ?, sheet = ?, max_rows = ?, next_run = ? where id = ?",
                       (json.dumps(when), sheet.strip(), int(max_rows), upcoming.isoformat(timespec="seconds") if upcoming else None, id))
        return self.get(id)

    def set_enabled(self, id: int, enabled: bool, now: Optional[datetime] = None) -> Schedule:
        schedule = self.get(id)
        upcoming = next_time(schedule.when, now or datetime.now()) if enabled else None
        with self.lock, self._db() as db:
            db.execute("update schedules set enabled = ?, next_run = ? where id = ?",
                       (int(enabled), upcoming.isoformat(timespec="seconds") if upcoming else None, id))
        return self.get(id)

    def set_next(self, id: int, upcoming: Optional[datetime]) -> None:
        with self.lock, self._db() as db:
            db.execute("update schedules set next_run = ? where id = ?", (upcoming.isoformat(timespec="seconds") if upcoming else None, id))

    def delete(self, id: int) -> None:
        with self.lock, self._db() as db:
            for table, column in (("schedules", "id"), ("history", "schedule"), ("done_rows", "schedule")):
                db.execute(f"delete from {table} where {column} = ?", (id,))

    def for_automation(self, automation: str) -> list[Schedule]:
        return [s for s in self.all() if s.automation == automation]

    # ------------------------------------------------------------------ history
    def record(self, schedule: int, due: str, state: str, message: str = "", run: Optional[int] = None) -> int:
        with self.lock, self._db() as db:
            cur = db.execute("insert into history (schedule, due, at, state, message, run) values (?, ?, ?, ?, ?, ?)",
                             (schedule, due, datetime.now().isoformat(timespec="seconds"), state, message, run))
            db.execute("delete from history where schedule = ? and id not in (select id from history where schedule = ? order by id desc limit 20)",
                       (schedule, schedule))
            return cur.lastrowid

    def finish(self, entry: int, state: str, message: str) -> None:
        with self.lock, self._db() as db:
            db.execute("update history set state = ?, message = ? where id = ?", (state, message, entry))

    def history(self, schedule: int) -> list[dict]:
        with self.lock, self._db() as db:
            return [dict(r) for r in db.execute("select * from history where schedule = ? order by id desc", (schedule,))]

    def missed_since(self, since: str) -> list[dict]:
        with self.lock, self._db() as db:
            return [dict(r) for r in db.execute("select * from history where state = 'missed' and at >= ? order by due", (since,))]

    # ------------------------------------------------------------------ rows already done
    def done(self, schedule: int) -> set[str]:
        with self.lock, self._db() as db:
            return {r["row"] for r in db.execute("select row from done_rows where schedule = ?", (schedule,))}

    def mark_done(self, schedule: int, rows: list[str]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.lock, self._db() as db:
            db.executemany("insert or ignore into done_rows (schedule, row, at) values (?, ?, ?)", [(schedule, r, now) for r in rows])

    def forget_done(self, schedule: int) -> None:
        with self.lock, self._db() as db:
            db.execute("delete from done_rows where schedule = ?", (schedule,))

    # ------------------------------------------------------------------ when ANCHOR was last open
    def alive(self, now: Optional[datetime] = None) -> None:
        with self.lock, self._db() as db:
            db.execute("insert or replace into meta (key, value) values ('alive', ?)", ((now or datetime.now()).isoformat(timespec="seconds"),))

    def last_alive(self) -> Optional[datetime]:
        with self.lock, self._db() as db:
            row = db.execute("select value from meta where key = 'alive'").fetchone()
        return datetime.fromisoformat(row["value"]) if row else None
