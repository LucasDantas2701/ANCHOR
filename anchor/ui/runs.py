"""
Runs started from the interface: a queue that runs one at a time, what each run says, and the
questions it asks the person.

A run calls the same functions as the command line (run_automation for a saved automation, the
Agent for a one-off request); only the pieces that ask the person are different: here a question
waits for an answer from the interface instead of the terminal. One run at a time: the model has
one GPU.
"""
from __future__ import annotations

import base64
import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from anchor.engine.disambiguation.types import ChoiceRequest, UserChoice
from anchor.engine.sensitive import ConfirmationRequest, Decision

QUESTION_POLL = 0.25        # how often a waiting question looks for an answer or a stop


class RunStopped(Exception):
    """The person stopped the run: raised at the run's next report, like Ctrl+C in the terminal."""


@dataclass
class Job:
    id: int
    kind: str                                    # "automation" | "request"
    title: str                                   # the automation's name, or the request
    spec: dict                                   # what to run (name and values, or request, url and profile)
    state: str = "queued"                        # queued, running, waiting, checked, not_done, stopped, error
    events: list = field(default_factory=list)   # what the run said and asked, in order
    question: Optional[dict] = None              # the open question, if any
    answer: Optional[dict] = None
    result: Optional[dict] = None
    activity: Optional[dict] = None               # what the AI is doing right now (phase, since, tokens)
    details: list = field(default_factory=list)   # each planning: what the model read and answered (local only)
    about: dict = field(default_factory=dict)      # the details file's header: version, model, Ollama, browser
    tabs: list = field(default_factory=list)       # the run's tabs and windows: title, address, which one ANCHOR uses
    viewing: Optional[int] = None                 # the tab the person chose to see (None: the one ANCHOR uses)
    frame: Optional[tuple] = None                 # the live view's last image: (number, jpeg bytes)
    watched: float = 0.0                          # when the live view last asked for an image
    tick: Optional[Callable[[], None]] = None     # the run's own thread: keeps the live view going
    inputs: deque = field(default_factory=deque)   # clicks and keys from the live view, for the browser
    frame_meta: Optional[dict] = None             # the page's size behind the live view's image
    queued_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))   # when it joined the queue
    started: str = ""                              # when it began
    finished: str = ""                             # when it ended
    found: Any = None                             # what a question waited for besides an answer (a pointed element)
    learned: Optional[dict] = None                # a checked request's steps and goals, to save as an automation
    keep_note: Optional[Callable[[str], None]] = None   # an automation's: keeps what the person said for next runs
    unsaved_notes: list = field(default_factory=list)   # what the person explained ("none of these") and did not keep
    on_end: Optional[Callable] = None                   # called with the job when it ends (a schedule records it)
    pump: Optional[Callable[[], None]] = None     # lets the browser's events through while a question waits
    stop: bool = False
    created: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    answered: threading.Event = field(default_factory=threading.Event, repr=False)

    def add(self, event_type: str, /, **data) -> dict:
        with self.lock:
            event = {"seq": len(self.events) + 1, "type": event_type, "at": time.strftime("%H:%M:%S"), **data}
            self.events.append(event)
            return event

    def watching(self) -> bool:
        """Someone has the live view open (it asks for an image several times a second)."""
        return time.time() - self.watched < 3.0

    def _tick(self) -> None:
        if self.tick is not None:
            try:
                self.tick()
            except Exception:
                pass                              # the live view never stops a run

    def say(self, line: str) -> None:
        """The run's report: each line goes to the interface. A stop takes effect here."""
        self._tick()
        if self.stop:
            raise RunStopped()
        line = line.strip("\n")
        if line.strip():
            self.add("line", text=line.strip())

    def takes_input(self) -> bool:
        """The browser takes the person's clicks and keys only while a login or a pointing waits for them."""
        question = self.question
        return question is not None and question.get("kind") in ("login", "point")

    def ask(self, kind: str, until: Optional[Callable[[], Any]] = None, **data) -> Optional[dict]:
        """
        Asks the person and waits. None when the run is stopped while waiting. With `until`, the
        wait also ends when it returns something (kept in `found`): an element pointed at.
        """
        self.found = None
        if self.stop:
            return None
        with self.lock:
            number = sum(e["type"] == "question" for e in self.events) + 1
            self.question, self.answer = {"number": number, "kind": kind, "keeps_notes": self.keep_note is not None, **data}, None
            self.answered.clear()
        previous, self.state = self.state, "waiting"
        self.add("question", **self.question)
        while not self.answered.is_set():
            if self.stop:
                break
            self._tick()
            if self.pump is not None:             # the browser keeps running (the live view, a login)
                try:
                    self.pump()
                except Exception:
                    self.answered.wait(QUESTION_POLL)
            else:
                self.answered.wait(QUESTION_POLL)
            if until is not None:
                found = until()
                if found is not None:
                    self.found = found
                    break
        with self.lock:
            answer, self.question = self.answer, None
            self.inputs.clear()                   # nothing typed for this question reaches a later one
        self.state = previous if not self.stop else self.state
        self.add("answered", number=number, answer=answer)
        return answer

    def give(self, number: int, answer: dict) -> bool:
        """The interface's answer to the open question (False if there is none with that number)."""
        with self.lock:
            if not self.question or self.question["number"] != number:
                return False
            self.answer = answer
        self.answered.set()
        return True

    def _suggestion(self) -> Optional[dict]:
        """After an automation's run that was not done: a note to offer for next time, in the person's
        own words (what they explained and did not keep), with the failure's reason beside it. The AI
        never writes it."""
        if self.kind != "automation" or not self.result or self.result.get("state") not in ("not_done", "error"):
            return None
        return {"text": self.unsaved_notes[-1] if self.unsaved_notes else "", "reason": self.result.get("message", "")}

    def view(self, after: int = 0) -> dict:
        with self.lock:
            activity = dict(self.activity, seconds=round(time.time() - self.activity["since"])) if self.activity else None
            return {"id": self.id, "kind": self.kind, "title": self.title, "state": self.state,
                    "question": self.question, "result": self.result, "spec": _public(self.spec), "activity": activity,
                    "can_save": self.kind == "request" and self.state == "checked" and self.learned is not None,
                    "tabs": self.tabs, "viewing": self.viewing,
                    "suggest_note": self._suggestion(),
                    "events": [e for e in self.events if e["seq"] > after]}


def _public(spec: dict) -> dict:
    """What the interface may show of a run's spec (everything but the browser's folder)."""
    return {k: v for k, v in spec.items() if k not in ("browser_dir",)}


# --- The questions, asked through the interface --------------------------------------------------

class WebConfirmer:
    """A sensitive action: Allow (kept), Don't allow (kept), or Not now (asked again next time)."""

    def __init__(self, job: Job, remembers: bool):
        self.job, self.remembers = job, remembers

    def confirm(self, request: ConfirmationRequest) -> bool:
        near = " ".join(request.element.split())
        answer = self.job.ask("confirm", category=request.category, element=request.element,
                              shown=request.shown or (near[:70] + ("…" if len(near) > 70 else "")),
                              near=near[:160] + ("…" if len(near) > 160 else ""),
                              description=request.description, remembers=self.remembers)
        choice = (answer or {}).get("choice")
        if choice == "allow":
            return Decision(True)
        if choice == "deny":
            return Decision(False)
        return Decision(False, save=False)


class WebDisambiguator:
    """Which element: a candidate by number, pointing at it (on the live view), or skipping the step."""

    def __init__(self, job: Job):
        self.job = job

    def capture_click(self, page, timeout_s: float = 120):
        """The person points at the element on the live view: the page listens, the run delivers the click."""
        from anchor.engine.disambiguation.page_tools import (
            cancel_capture,
            read_capture,
            start_capture,
        )
        start_capture(page, timeout_s)

        def pointed():
            done, match = read_capture(page)
            return ("done", match) if done else None

        self.job.ask("point", until=pointed)
        if self.job.found is None:                # cancelled, or the run was stopped
            try:
                cancel_capture(page)
            except Exception:
                pass
            return None
        return self.job.found[1]

    def notify(self, message: str) -> None:
        from anchor.i18n import t
        if message != t("dis.point_now"):         # the interface's own panel says where to click
            self.job.add("line", text=message)

    def choose(self, request: ChoiceRequest) -> UserChoice:
        shot = base64.b64encode(request.screenshot).decode() if request.screenshot else None
        answer = self.job.ask("choose", action=request.action, description=request.description,
                              reason=request.reason, can_point=request.can_point, screenshot=shot,
                              candidates=[{"number": c.number, "kind": c.kind, "name": c.name, "near": c.near}
                                          for c in request.candidates])
        answer = answer or {}
        if answer.get("choice") == "candidate" and isinstance(answer.get("number"), int) \
                and 1 <= answer["number"] <= len(request.candidates):
            return UserChoice("candidate", answer["number"])
        if answer.get("choice") == "none":                 # none of these, and maybe why: the planner hears it
            note = " ".join(str(answer.get("note") or "").split())[:300]
            if note and answer.get("keep") and self.job.keep_note is not None:
                self.job.keep_note(note)                   # an automation's note: sent to its planner on every run
            elif note:
                self.job.unsaved_notes.append(note)        # offered again as a note if the run is not done
            return UserChoice("none", note=note or None)
        if answer.get("choice") == "login":                # the page needs a login first
            return UserChoice("login")
        if answer.get("choice") == "point" and request.can_point:
            return UserChoice("point")
        return UserChoice("skip")


class WebLoginWaiter:
    """The task needs a login: the person logs in in the browser window, then says so."""

    def __init__(self, job: Job, can_log_in: bool = True):     # with the live view, a login is always possible
        self.job, self.can_log_in = job, can_log_in

    def wait(self, url: str, signup: bool = False) -> bool:
        if not self.can_log_in:          # the browser has no window: no one can log in in it
            self.job.add("line", text="This page needs you to log in, and the browser window is hidden. "
                                      "Run it again with \"Show the browser window\" on.")
            return False
        answer = self.job.ask("login", url=url, signup=signup)
        return (answer or {}).get("choice") == "done"


# --- The queue ----------------------------------------------------------------------------------

Runner = Callable[[Job], dict]       # does the run; returns {"state", "message", ...}


class RunManager:
    """Runs one job at a time, in the order they came; keeps the last ones to show."""

    KEEP = 30

    def __init__(self, runner: Runner):
        self.runner = runner
        self.jobs: dict[int, Job] = {}
        self.queue: deque[Job] = deque()
        self.ids = itertools.count(1)
        self.cond = threading.Condition()
        self.current: Optional[Job] = None
        threading.Thread(target=self._work, daemon=True, name="anchor-runs").start()

    def submit(self, kind: str, title: str, spec: dict) -> Job:
        job = Job(next(self.ids), kind, title, spec)
        with self.cond:
            self.jobs[job.id] = job
            self.queue.append(job)
            self._forget_old()
            self.cond.notify()
        return job

    def position(self, job: Job) -> int:
        """0 when running; 1 when next; and so on."""
        with self.cond:
            if job is self.current:
                return 0
            return next((i + 1 for i, j in enumerate(self.queue) if j is job), 0)

    def stop(self, job: Job) -> None:
        with self.cond:
            job.stop = True
            if job in self.queue:                 # not started: it just leaves the queue
                self.queue.remove(job)
                job.state = "stopped"
                job.result = {"state": "stopped", "message": "Taken out of the queue before it started."}
                job.finished = time.strftime("%Y-%m-%dT%H:%M:%S")
                if job.on_end is not None:
                    try:
                        job.on_end(job)
                    except Exception:
                        pass
        job.answered.set()

    def list(self) -> list[dict]:
        with self.cond:
            jobs = sorted(self.jobs.values(), key=lambda j: j.id, reverse=True)
        return [{"id": j.id, "kind": j.kind, "title": j.title, "state": j.state, "position": self.position(j),
                 "name": j.spec.get("name"), "created": j.queued_at, "started": j.started, "finished": j.finished,
                 "message": (j.result or {}).get("message", ""), "scheduled": bool(j.spec.get("schedule"))} for j in jobs]

    def _forget_old(self) -> None:
        done = [j for j in sorted(self.jobs.values(), key=lambda j: j.id) if j.state not in ("queued", "running", "waiting")]
        for j in done[:max(0, len(self.jobs) - self.KEEP)]:
            self.jobs.pop(j.id, None)

    def _work(self) -> None:
        while True:
            with self.cond:
                while not self.queue:
                    self.cond.wait()
                job = self.current = self.queue.popleft()
            job.state = "running"
            job.started = time.strftime("%Y-%m-%dT%H:%M:%S")
            job.add("state", state="running")
            try:
                result = self.runner(job)
            except RunStopped:
                result = {"state": "stopped", "message": "Stopped by you."}
            except Exception as exc:              # the run broke: say so, and keep the queue going
                result = {"state": "error", "message": f"The run could not go on: {exc}"}
            if job.stop and result.get("state") not in ("checked",):
                result["state"] = "stopped"
            from .explain import explain
            result = explain(result)
            job.activity = None
            job.result = result
            if job.on_end is not None:            # recorded before the run shows as ended (a schedule's history)
                try:
                    job.on_end(job)
                except Exception:                 # a schedule's record must not stop the queue
                    pass
            job.state = result.get("state", "not_done")
            job.finished = time.strftime("%Y-%m-%dT%H:%M:%S")
            job.add("result", **result)
            with self.cond:
                self.current = None
