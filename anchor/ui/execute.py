"""
Doing a run from the interface, the way the command line does it: the same browser setup, the
same run_automation and Agent, the same rules. Only the questions go to the interface.
"""
from __future__ import annotations

import base64
import dataclasses
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from anchor.agent.agent import Agent
from anchor.automations.model import AutomationError, AutomationStore
from anchor.automations.runner import run_automation
from anchor.browser.launch import open_context
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation.describe import describe
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.planner import ConfigError, PlanError, get_profile, page_elements

from .runs import Job, RunStopped, WebConfirmer, WebDisambiguator, WebLoginWaiter


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

    def viewed(self):
        """The tab the person chose to see (and to click on during a login), or else the one ANCHOR uses."""
        current = self.current()
        chosen = self.job.viewing
        if chosen is not None:
            pages = [p for p in current.context.pages if not p.is_closed()]
            if 0 <= chosen < len(pages):
                return pages[chosen]
            self.job.viewing = None                      # the chosen tab was closed: back to ANCHOR's
        return current

    def list_tabs(self) -> None:
        """The run's tabs and windows, for the interface's strip: title, address, and which one ANCHOR uses."""
        current = self.current()
        tabs = []
        for i, p in enumerate(q for q in current.context.pages if not q.is_closed()):
            try:
                title = p.title()
            except Exception:
                title = ""
            tabs.append({"index": i, "title": (title or p.url)[:50], "url": p.url, "anchor": p is current})
        self.job.tabs = tabs

    def maintain(self) -> None:
        try:
            self.list_tabs()
        except Exception:
            pass
        page = self.viewed()
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
            self.job.frame_meta = params.get("metadata")
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


# Keys the live view may press besides typing text: moving in a form and editing what was typed.
KEYS = {"Enter", "Tab", "Shift+Tab", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft",
        "ArrowRight", "Home", "End", "PageUp", "PageDown", "Space", "Control+a", "Meta+a"}


def deliver(job: Job, page) -> None:
    """
    The person's clicks and keys from the live view, done in the browser (from the run's own
    thread). Never recorded: what is typed goes to the page and nowhere else.
    """
    while job.inputs:
        event = job.inputs.popleft()
        kind = event.get("type")
        if kind in ("click", "scroll"):
            meta = job.frame_meta or {}
            width = meta.get("deviceWidth") or (page.viewport_size or {}).get("width") or 1280
            height = meta.get("deviceHeight") or (page.viewport_size or {}).get("height") or 720
            x = min(max(float(event.get("x", 0)), 0.0), 1.0) * width
            y = min(max(float(event.get("y", 0)), 0.0), 1.0) * height
            if kind == "click":
                page.mouse.click(x, y)
            else:
                page.mouse.move(x, y)
                page.mouse.wheel(0, max(-2000, min(2000, float(event.get("dy", 0)))))
        elif kind == "text" and isinstance(event.get("text"), str):
            page.keyboard.insert_text(event["text"][:2000])
        elif kind == "key" and event.get("key") in KEYS:
            page.keyboard.press(event["key"])


def _attach(job: Job, executor: ActionExecutor) -> LiveView:
    """The interface's eyes and hands on a run: the live view, the person's clicks and keys while a
    login or a pointing waits, and, after each action, what it was done on."""
    live = LiveView(job, lambda: executor.page)
    job.tick = live.maintain

    def pump():
        deliver(job, live.viewed())                      # clicks and keys go to the tab the person sees
        executor.page.wait_for_timeout(50)

    job.pump = pump

    last_url = [""]

    def element(match) -> str:
        seen = describe(match, 0, "en")
        near = " ".join(seen.near.split()[:4])
        near = f" near “{near}…”" if near and len(seen.near.split()) > 4 else (f" near “{near}”" if near else "")
        return f"{seen.kind} “{seen.name}”{near}"

    def used(result):
        match = getattr(result, "selected_element", None)
        if result.status == "success" and match is not None:
            job.add("used", text=element(match))
        elif result.status != "success" and (match is not None or result.error):
            # A step that failed: the element it tried (if any) and the whole message (a blocked click says what covers it).
            job.add("tried", text=element(match) if match is not None else "", error=(result.error or result.status)[:600])
        try:
            url = executor.page.url
        except Exception:
            url = ""
        if url and url != last_url[0]:
            if last_url[0]:
                job.add("page", text=url)
            last_url[0] = url

    executor.on_result = used
    return live


SHOWN_AT_END = """() => {
  const seen = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const texts = [...document.querySelectorAll('[role=alert], [role=status], [aria-live], .error, .alert, .toast, .message, .notice')]
    .filter(seen).map((e) => (e.innerText || '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
  return { title: document.title, messages: [...new Set(texts)].slice(0, 5).map((t) => t.slice(0, 160)) };
}"""


def page_at_end(page) -> dict:
    """What the page showed when a run stopped: its address, title and visible messages (alerts, errors, notices)."""
    try:
        seen = page.evaluate(SHOWN_AT_END)
        return {"url": page.url, "title": seen.get("title", ""), "messages": seen.get("messages", [])}
    except Exception:
        return {}


def about(spec: dict, hidden: bool) -> dict:
    """The details file's header: ANCHOR's version, the model, Ollama's version and the browser's mode."""
    from anchor import __version__
    out = {"anchor": __version__, "browser": "hidden (live view)" if hidden else "window"}
    try:
        profile = get_profile(spec.get("profile", "ollama-small"))
        out.update(profile=profile.name, model=profile.model)
        if profile.base_url and ("11434" in profile.base_url or profile.api == "ollama"):
            import json
            import urllib.request
            root = profile.base_url.split("/v1")[0].rstrip("/")
            with urllib.request.urlopen(root + "/api/version", timeout=2) as answer:
                out["ollama"] = json.loads(answer.read().decode()).get("version", "")
    except Exception:
        pass
    return out


def _ended(job: Job, result, executor: ActionExecutor) -> dict:
    """When a run did not end well: what the page showed (logged, and kept in the result)."""
    if result.ok:
        return {}
    shown = page_at_end(executor.page)
    if shown:
        job.add("ended_on", text=shown.get("title", ""), url=shown.get("url", ""), messages=shown.get("messages", []))
    return {"ended_on": shown} if shown else {}


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

    def __init__(self, store: AutomationStore, headless: bool = False, output_dir: str | Path = "output", vault=None):
        self.store, self.headless, self.output_dir = store, headless, Path(output_dir)
        self.vault = vault                       # saved logins: tried first when a run reaches a login page

    def _login(self, job: Job, executor) -> object:
        """The run's login waiter: the login saved for the page's exact site first, then the person."""
        if self.vault is None:
            return WebLoginWaiter(job)
        from anchor.vault.fill import VaultLoginWaiter
        return VaultLoginWaiter(self.vault, lambda: executor.page, fallback=WebLoginWaiter(job), report=job.say)

    def _hidden(self, job: Job) -> bool:
        """The browser runs hidden, watched through the live view, unless the person asked for its window too."""
        return self.headless or not job.spec.get("show_browser", False)

    def _mode(self, job: Job | None = None, show: bool | None = None) -> str:
        """headless in the tests; otherwise a real window, outside the screen unless the person asked to see it."""
        if self.headless:
            return "headless"
        visible = job.spec.get("show_browser", False) if show is None else show
        return "window" if visible else "offscreen"

    def __call__(self, job: Job) -> dict:
        try:
            if job.kind == "automation":
                return self.saved(job)
            if job.kind == "login":
                return self.login(job)
            if job.kind == "plan":
                return self.preview(job)
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
        job.about = about({"profile": automation.profile}, hidden)

        with sync_playwright() as p:
            # Each automation keeps its own browser profile, so a login done once is kept.
            folder = automation.browser_profile or (None if spec.get("fresh_browser") else str(store.folder(name) / "browser"))
            context = open_context(p, self._mode(job), folder)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=True, memory=ChoiceMemory(store.memory_path(name)))
                live = _attach(job, executor)
                job.keep_note = lambda text: store.add_note(name, text)
                if spec.get("rows"):
                    return self._rows(job, store, name, automation, page, executor, make_planner)
                page.goto(automation.url)
                result, mode, run_id = run_automation(
                    store, name, page, executor, make_planner, report=job.say,
                    relearn=bool(spec.get("relearn")), heal=True, params=spec.get("values") or {},
                    confirm=WebConfirmer(job, remembers=True), login=self._login(job, executor),
                    unattended=bool(spec.get("unattended")))
                ended = _ended(job, result, executor)
            finally:
                if "live" in locals():
                    _detach(job, live)
                context.close()
        return _outcome(result, mode=mode, run=run_id, **ended)

    def _rows(self, job: Job, store, name, automation, page, executor, make_planner) -> dict:
        """A spreadsheet: the automation once per row, in the same browser, with the same questions as a
        single run. Stopping ends the rows still to go; the result has one line per row."""
        rows = job.spec["rows"]
        outcomes, steps, seconds, calls, mode = [], 0, 0.0, 0, "replay"
        stopped = False
        for number, values in enumerate(rows, 1):
            job.add("row", number=number, total=len(rows), text=" · ".join(values.get(p, "") for p in automation.parameters))
            try:
                page.goto(automation.url)
                result, row_mode, _ = run_automation(
                    store, name, page, executor, make_planner, report=job.say,
                    relearn=bool(job.spec.get("relearn")) and number == 1, heal=True, params=values,
                    confirm=WebConfirmer(job, remembers=True), login=self._login(job, executor),
                    unattended=bool(job.spec.get("unattended")))
            except RunStopped:
                outcomes.append({"number": number, "state": "stopped", "message": "Stopped by you.", "values": values})
                stopped = True
                break
            except Exception as exc:                      # this row could not run: say so, and go on with the next
                outcomes.append({"number": number, "state": "error", "message": f"It could not run: {exc}", "values": values})
                continue
            row = _outcome(result)
            outcomes.append({"number": number, "state": row["state"], "message": result.message, "values": values})
            steps += row["steps"]; seconds += row["seconds"]; calls += row["model_calls"]
            mode = row_mode if number == 1 else mode
            if job.stop:
                stopped = True
                break
        for number in range(len(outcomes) + 1, len(rows) + 1):
            outcomes.append({"number": number, "state": "stopped", "message": "Not run: stopped before it.", "values": rows[number - 1]})
        done = sum(o["state"] == "checked" for o in outcomes)
        state = "stopped" if stopped else ("checked" if done == len(rows) else "not_done")
        return {"state": state, "status": "rows", "message": f"{done} of {len(rows)} rows done.", "rows": outcomes,
                "steps": steps, "seconds": round(seconds, 1), "model_calls": calls, "mode": mode}

    def login(self, job: Job) -> dict:
        """
        "Log in to this site": the automation's own browser, in a window (unless the tests run it
        hidden), on its site; the person logs in, and the session stays in the automation's profile.
        """
        name = job.spec["name"]
        automation = self.store.load(name)
        folder = automation.browser_profile or str(self.store.folder(name) / "browser")
        with sync_playwright() as p:
            context = open_context(p, self._mode(show=True), folder)
            page = context.pages[0] if context.pages else context.new_page()
            executor = ActionExecutor(page)
            live = _attach(job, executor)
            try:
                page.goto(automation.url)
                job.add("line", text="A browser window opened on the automation's site: log in there, or on the live view."
                        if not self.headless else "The automation's site is open: log in on the live view.")
                answer = job.ask("login", url=automation.url, signup=False, window=not self.headless)
            finally:
                _detach(job, live)
                context.close()
        if (answer or {}).get("choice") == "done":
            return {"state": "checked", "message": "You logged in. The automation's runs will use this session."}
        return {"state": "stopped", "message": "Nothing was changed."}

    def preview(self, job: Job) -> dict:
        """The plan the AI would make for a request, on the page, without doing any of it."""
        spec = job.spec
        profile = get_profile(spec["profile"])
        planner = StepwisePlanner(job, lambda progress: profile.planner(on_progress=progress))
        with sync_playwright() as p:
            context = open_context(p, self._mode(show=False))
            page = context.new_page()
            try:
                job.say("Opening the page...")
                page.goto(spec["url"])
                job.say("Reading the page and asking the AI for a plan. Nothing will be done on the page.")
                elements = page_elements(ElementResolver(page), request=spec["request"],
                                         language=planner.language_for(spec["request"]))
                try:
                    plan = planner.plan(spec["request"], page.url, elements)
                except PlanError as exc:
                    return {"state": "not_done", "message": f"could not generate the plan: {exc}"}
            finally:
                context.close()
        steps = [{"action": s.action, "description": s.description, "value": s.value, "goal": s.goal} for s in plan.steps]
        goals = [{"id": g.id, "description": g.description, "conclusive": g.conclusive} for g in plan.goals]
        return {"state": "planned", "message": f"The AI would do {len(steps)} steps.", "plan": {"steps": steps, "goals": goals},
                "seconds": round(plan.latency_s, 1), "model_calls": plan.attempts}

    def request(self, job: Job) -> dict:
        spec = job.spec
        profile = get_profile(spec["profile"])
        planner = StepwisePlanner(job, lambda progress: profile.planner(on_progress=progress))
        hidden = self._hidden(job)
        job.about = about(spec, hidden)
        with sync_playwright() as p:
            context = open_context(p, self._mode(job))
            page = context.new_page()
            try:
                page.goto(spec["url"])
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=True, memory=ChoiceMemory(spec.get("memory", "memory/agent.json")),   # the same file as the command line
                                          confirmer=WebConfirmer(job, remembers=False))
                live = _attach(job, executor)
                agent = Agent(page, planner, executor, report=job.say, login=self._login(job, executor), output_dir=self.output_dir)
                result = agent.run(spec["request"])
                if result.ok:
                    # What an automation would keep from this run, as its first run would: the steps that
                    # worked and the goals they reached.
                    done = [r.step for r in result.records if r.status == "success"]
                    used = {s.goal for s in done if s.goal}
                    job.learned = {"steps": [dataclasses.asdict(s) for s in done],
                                   "goals": [dataclasses.asdict(g) for g in agent._goals.values() if g.id in used],
                                   "language": agent.language}
                ended = _ended(job, result, executor)
            finally:
                if "live" in locals():
                    _detach(job, live)
                context.close()
        return _outcome(result, mode="request", **ended)
