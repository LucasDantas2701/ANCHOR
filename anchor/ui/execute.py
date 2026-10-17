"""
Doing a run from the interface, the way the command line does it: the same browser setup, the
same run_automation and Agent, the same rules. Only the questions go to the interface.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.agent.agent import Agent
from anchor.automations.model import AutomationError, AutomationStore
from anchor.automations.runner import run_automation
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.planner import ConfigError, get_profile

from .runs import Job, WebConfirmer, WebDisambiguator, WebLoginWaiter


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
    """Runs jobs for the RunManager. headless: the browser has no window (the tests; later, the live view)."""

    def __init__(self, store: AutomationStore, headless: bool = False, output_dir: str | Path = "output"):
        self.store, self.headless, self.output_dir = store, headless, Path(output_dir)

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
            return get_profile(auto.profile).planner(prompt_language=auto.prompt_language)

        with sync_playwright() as p:
            # Each automation keeps its own browser profile, so a login done once is kept.
            folder = automation.browser_profile or (None if spec.get("fresh_browser") else str(store.folder(name) / "browser"))
            if folder:
                context = p.chromium.launch_persistent_context(folder, headless=self.headless)
                page = context.pages[0] if context.pages else context.new_page()
            else:
                context = p.chromium.launch(headless=self.headless).new_context()
                page = context.new_page()
            try:
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=not self.headless, memory=ChoiceMemory(store.memory_path(name)))
                page.goto(automation.url)
                result, mode, run_id = run_automation(
                    store, name, page, executor, make_planner, report=job.say,
                    relearn=bool(spec.get("relearn")), heal=True, params=spec.get("values") or {},
                    confirm=WebConfirmer(job, remembers=True), login=WebLoginWaiter(job))
            finally:
                context.close()
        return _outcome(result, mode=mode, run=run_id)

    def request(self, job: Job) -> dict:
        spec = job.spec
        profile = get_profile(spec["profile"])
        planner = profile.planner()
        with sync_playwright() as p:
            context = p.chromium.launch(headless=self.headless).new_context()
            page = context.new_page()
            try:
                page.goto(spec["url"])
                executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=WebDisambiguator(job),
                                          can_point=not self.headless, memory=ChoiceMemory(spec.get("memory", "memory.json")),
                                          confirmer=WebConfirmer(job, remembers=False))
                result = Agent(page, planner, executor, report=job.say, login=WebLoginWaiter(job),
                               output_dir=self.output_dir).run(spec["request"])
            finally:
                context.close()
        return _outcome(result, mode="request")
