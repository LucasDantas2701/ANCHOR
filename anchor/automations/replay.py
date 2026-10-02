"""
Replaying an approved plan, without calling the LLM, and healing it.

The agent sees the ReplayPlanner as any other planner: it hands out the saved
steps, and on each replan (the page changed, a pop-up opened) the steps still
missing. If a saved step fails even after the choice memory, the heuristic
and the user, the saved plan no longer matches the site:

  - with a healer (the default), the ReplayPlanner hands over to the LLM, which
    plans the rest from the page as it is now; if the run succeeds, the runner
    corrects the saved plan and records the recovery;
  - without one (--no-heal), SavedPlanBroken stops the replay with the reason.
"""

from __future__ import annotations

from typing import Callable, Optional

from anchor.i18n import t
from anchor.planner import Goal, Plan, Step
from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, mt

_DONE = tuple(mt("hist.done", lang, step="") for lang in ("pt", "en"))
_BROKEN = tuple(mt(key, lang, step="", reason="").split("—")[0].rstrip()
                for key in ("hist.failed", "hist.blocked") for lang in ("pt", "en"))


class SavedPlanBroken(RuntimeError):
    """A step of the approved plan failed: the site changed."""


class ReplayPlanner:
    model = "replay"

    def __init__(self, steps: list[Step], goals: list[Goal], language: str = DEFAULT_PROMPT_LANGUAGE,
                 make_healer: Optional[Callable[[], object]] = None,
                 report: Optional[Callable[[str], None]] = None):
        self.steps, self.goals, self.language = list(steps), list(goals), language
        self.make_healer, self.report = make_healer, report or (lambda _: None)
        self.healer = None
        self.calls = 0
        self.broken = False           # a saved step failed
        self.broken_reason = ""
        self.broken_at = 0            # how many saved steps worked before it

    @property
    def uses_llm(self) -> bool:
        """False while replaying; True once the LLM took over to heal the plan."""
        return self.healer is not None

    def language_for(self, request: str) -> str:
        return self.language

    def plan(self, request, url, page_elements=None, history=None, **kwargs) -> Plan:
        self.calls += 1
        history = history or []
        if not history:
            return Plan(steps=list(self.steps), goals=list(self.goals), model=self.model)
        if self.healer is not None:
            return self.healer.plan(request, url, page_elements, history, **kwargs)

        done = sum(1 for h in history if h.startswith(_DONE))
        failures = [h for h in history if h.startswith(_BROKEN)]
        if failures:
            self.broken, self.broken_reason, self.broken_at = True, failures[-1], done
            if self.make_healer is None:
                raise SavedPlanBroken(failures[-1])
            self.report(t("auto.healing"))
            self.healer = self.make_healer()
            known = set(kwargs.pop("known_goals", None) or ()) | {g.id for g in self.goals}
            if known:
                kwargs["known_goals"] = known
            return self.healer.plan(request, url, page_elements, history, **kwargs)
        return Plan(steps=list(self.steps[done:]), model=self.model)
