"""
Doing a run from the interface, the way the command line does it: the same browser setup, the
same run_automation and Agent, the same rules. Only the questions go to the interface.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from anchor.agent.agent import Agent
from anchor.automations.model import AutomationError, AutomationStore
from anchor.automations.runner import run_automation
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation.describe import describe
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.planner import ConfigError, get_profile

from .runs import Job, WebConfirmer, WebDisambiguator, WebLoginWaiter


class StepwisePlanner:
    """
    The planner, with what it is doing shown in the interface: a live line while the AI thinks
    and writes, and, for each plan the AI gave that was not usable, why, as soon as it is known.
    """

    def __init__(self, job: Job, make):
        self.job = job
        self.planner = make(self._progress)

    @property
    def language(self) -> str:
        return self.planner.language

    def language_for(self, request: str) -> str:
        return self.planner.language_for(request)

    def _progress(self, phase: str, tokens: int) -> None:
        activity = self.job.activity
        if activity is not None:
            if tokens < activity.get("tokens", 0):          # a new attempt starts from nothing
                activity["attempt"] = activity.get("attempt", 1) + 1
            activity.update(phase=phase, tokens=tokens)

    def plan(self, *args, **kwargs):
        self.job.activity = {"phase": "waiting", "tokens": 0, "attempt": 1, "since": time.time()}
        named = dict(zip(("request", "url", "page", "history"), args), **kwargs)
        record = {"at": time.strftime("%H:%M:%S"), "request": named.get("request"), "url": named.get("url"),
                  "page": named.get("page") if named.get("page") is not None else named.get("page_elements"),
                  "history": named.get("history"), "refused": [], "answer": None, "error": None}
        try:
            plan = self.planner.plan(*args, **kwargs)
            record["answer"] = getattr(plan, "raw", None) or repr(plan)
            return plan
        except Exception as exc:
            record["error"] = str(exc)
            raise
        finally:
            self.job.activity = None
            attempts = getattr(self.planner, "last_attempts", [])
            reasons = getattr(self.planner, "last_refusals", None) or [why for _, why in attempts]
            record["refused"] = [{"answer": raw, "why": why} for raw, why in attempts]
            self.job.details.append(record)
            for number, why in enumerate(reasons, 1):
                self.job.add("line", text=f"The AI's plan (attempt {number}) was not usable: {why}")


class LiveView:
    """
    The browser's picture for the interface's live view, only while someone watches it: started,
    moved to the current tab and stopped from the run's own thread (Playwright's rule), at each
    report and while a question waits.
    """

    def __init__(self, job: Job, current: Callable):
        self.job, self.current = job, current
        self.session = self.page = None
        self.count = 0

    def maintain(self) -> None:
        page = self.current()
        if self.job.watching():
            if self.session is None or self.page is not page:
                self._start(page)
        elif self.session is not None:
            self.stop()

    def _start(self, page) -> None:
        self.stop()
        session = page.context.new_cdp_session(page)

        def frame(params):
            self.count += 1
            self.job.frame = (self.count, base64.b64decode(params["data"]))
            try:
                session.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
            except Exception:
                pass

        session.on("Page.screencastFrame", frame)
        session.send("Page.startScreencast", {"format": "jpeg", "quality": 70, "maxWidth": 1280, "maxHeight": 800})
        self.session, self.page = session, page

    def stop(self) -> None:
        if self.session is not None:
            try:
                self.session.send("Page.stopScreencast")
                self.session.detach()
            except Exception:
                pass
        self.session = self.page = None


def _attach(job: Job, executor: ActionExecutor) -> LiveView:
    """The interface's eyes on a run: the live view, the browser's events while a question waits,
    and, after each action, what it was done on."""
    live = LiveView(job, lambda: executor.page)
    job.tick = live.maintain
    job.pump = lambda: executor.page.wait_for_timeout(100)

    def used(result):
        match = getattr(result, "selected_element", None)
        if result.status == "success" and match is not None:
            seen = describe(match, 0, "en")
            near = " ".join(seen.near.split()[:4])
            near = f" near “{near}…”" if near and len(seen.near.split()) > 4 else (f" near “{near}”" if near else "")
            job.add("used", text=f"{seen.kind} “{seen.name}”{near}")

    executor.on_result = used
    return live


def _detach(job: Job, live: LiveView) -> None:
    live.stop()
    job.tick = job.pump = None


def _outcome(result, **more) -> dict:
    if result.ok:
        state = "checked"
    elif getattr(result, "denied", False):       # the person said no to a sensitive action
        state = "stopped"
    else:                                        # failed, or the agent gave up ("cancelled")
        state = "not_done"
    return {"state": state, "status": result.status, "message": result.message,
            "steps": sum(r.status == "success" for r in result.records), "seconds": round(result.seconds, 1),
            "model_calls": result.llm_calls, **more}


class Executor:
    """
    Runs jobs for the RunManager. headless: the browser never has a window (the tests); otherwise
    each run says whether to show it ("show_browser", on by default).
    """

    def __init__(self, store: AutomationStore, headless: bool = False, output_dir: str | Path = "output"):
        self.store, self.headless, self.output_dir = store, headless, Path(output_dir)

    def _hidden(self, job: Job) -> bool:
        """The browser runs hidden, watched through the live view, unless the person asked for its window too."""
        return self.headless or not job.spec.get("show_browser", False)

    def __call__(self, job: Job) -> dict:
        try:
            if job.kind == "automation":
                return self.saved(job)
            return self.request(job)
        except (ConfigError, AutomationError) as exc:
            return {"state": "error", "message": str(exc)}

    def saved(self, job: Job) -> dict:
        spec, store = job.spec, self.store
        name = spec["name"]
        automation = store.load(name)

        def make_planner(auto):
            profile = get_profile(auto.profile)
            return StepwisePlanner(job, lambda progress: profile.planner(on_progress=progress, prompt_language=auto.prompt_language))

        hidden = self._hidden(job)

        with sync_playwright() as p:
            # Each automation keeps its own browser profile, so a login done once is kept.
            folder = automation.browser_profile or (None if spec.get("fresh_browser") else str(store.folder(name) / "browser"))
            if folder:
                context = p.chromium.launch_persistent_context(folder, headless=hidden)
                page = context.pages[0] if context.pages else context.new_page()
            else:
                context = p.chromium.launch(headless=hidden).new_context()
                page = context.new_page()
            try:
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=not hidden, memory=ChoiceMemory(store.memory_path(name)))
                live = _attach(job, executor)
                page.goto(automation.url)
                result, mode, run_id = run_automation(
                    store, name, page, executor, make_planner, report=job.say,
                    relearn=bool(spec.get("relearn")), heal=True, params=spec.get("values") or {},
                    confirm=WebConfirmer(job, remembers=True), login=WebLoginWaiter(job, can_log_in=not hidden))
            finally:
                if "live" in locals():
                    _detach(job, live)
                context.close()
        return _outcome(result, mode=mode, run=run_id)

    def request(self, job: Job) -> dict:
        spec = job.spec
        profile = get_profile(spec["profile"])
        planner = StepwisePlanner(job, lambda progress: profile.planner(on_progress=progress))
        hidden = self._hidden(job)
        with sync_playwright() as p:
            context = p.chromium.launch(headless=hidden).new_context()
            page = context.new_page()
            try:
                page.goto(spec["url"])
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=not hidden, memory=ChoiceMemory(spec.get("memory", "memory/agent.json")),   # the same file as the command line
                                          confirmer=WebConfirmer(job, remembers=False))
                live = _attach(job, executor)
                result = Agent(page, planner, executor, report=job.say, login=WebLoginWaiter(job, can_log_in=not hidden),
                               output_dir=self.output_dir).run(spec["request"])
            finally:
                if "live" in locals():
                    _detach(job, live)
                context.close()
        return _outcome(result, mode="request")
