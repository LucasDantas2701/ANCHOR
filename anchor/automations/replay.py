"""
Replaying an approved plan, without calling the LLM.

The agent sees the ReplayPlanner as any other planner: it hands out the saved
steps, and on each replan (the page changed, a pop-up opened) the steps still
missing. If a saved step fails, the saved plan no longer matches the site, and
SavedPlanBroken stops the replay with the reason.
"""

from __future__ import annotations

from anchor.planner import Goal, Plan, Step
from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, mt

_DONE = tuple(mt("hist.done", lang, step="") for lang in ("pt", "en"))
_BROKEN = tuple(mt(key, lang, step="", reason="").split("—")[0].rstrip()
                for key in ("hist.failed", "hist.blocked") for lang in ("pt", "en"))


class SavedPlanBroken(RuntimeError):
    """A step of the approved plan failed: the site changed."""


class ReplayPlanner:
    model = "replay"
    uses_llm = False      # the agent does not count its answers as model calls

    def __init__(self, steps: list[Step], goals: list[Goal], language: str = DEFAULT_PROMPT_LANGUAGE):
        self.steps, self.goals, self.language = list(steps), list(goals), language
        self.calls = 0
        self.broken = False
        self.broken_reason = ""

    def language_for(self, request: str) -> str:
        return self.language

    def plan(self, request, url, page_elements=None, history=None, **_) -> Plan:
        self.calls += 1
        history = history or []
        if not history:
            return Plan(steps=list(self.steps), goals=list(self.goals), model=self.model)
        failures = [h for h in history if h.startswith(_BROKEN)]
        if failures:
            self.broken, self.broken_reason = True, failures[-1]
            raise SavedPlanBroken(failures[-1])
        done = sum(1 for h in history if h.startswith(_DONE))
        return Plan(steps=list(self.steps[done:]), model=self.model)
