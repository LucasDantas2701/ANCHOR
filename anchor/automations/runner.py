"""
Running a saved automation.

    learn  (no approved plan yet, or --relearn): the agent plans with the LLM; if the
           run succeeds, the steps that worked become the approved plan.
    replay (there is an approved plan): the plan is replayed without the LLM. If a saved
           step fails, the replay stops and reports where the site changed.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Optional

from anchor import __version__
from anchor.agent import Agent, AgentResult
from anchor.engine.action_executor import ActionExecutor
from anchor.i18n import t

from .model import ApprovedPlan, Automation, AutomationStore
from .replay import ReplayPlanner


def run_automation(
    store: AutomationStore,
    name: str,
    page,
    executor: ActionExecutor,
    make_planner: Callable[[Automation], object],
    report: Optional[Callable[[str], None]] = print,
    relearn: bool = False,
    **agent_options,
) -> tuple[AgentResult, str, str]:
    """Runs the automation; returns (result, mode, run id). mode: "learn" or "replay"."""
    automation = store.load(name)
    approved = None if relearn else store.load_plan(name)
    say = report or (lambda _: None)

    if approved is not None:
        mode = "replay"
        planner = ReplayPlanner(approved.steps, approved.goals, approved.language)
        say(t("auto.replaying", name=name, steps=len(approved.steps)))
    else:
        mode = "learn"
        planner = make_planner(automation)
        say(t("auto.learning", name=name))

    # The caller opens the automation's link (page.goto(automation.url)) before running it.
    agent = Agent(page, planner, executor, report=report, **agent_options)
    result = agent.run(automation.request)

    if mode == "replay" and getattr(planner, "broken", None):
        result.status = "failed"
        result.message = t("auto.broken", reason=planner.broken_reason)
        say(t("agent.ended", message=result.message))

    run_id = store.save_run(name, {
        "version": __version__, "mode": mode, "status": result.status, "message": result.message,
        "steps": [{"action": r.step.action, "description": r.step.description, "value": r.step.value,
                   "status": r.status, "resolved_by": r.resolved_by, "note": r.note} for r in result.records],
        "llm_calls": result.llm_calls, "replans": result.replans, "failures": result.failures,
        "interventions": result.interventions, "no_effect": result.no_effect, "seconds": result.seconds,
    })

    if mode == "learn" and result.ok:
        steps = [r.step for r in result.records if r.status == "success"]
        used = {s.goal for s in steps if s.goal}
        goals = [g for g in agent._goals.values() if g.id in used]
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=agent.language))
        say(t("auto.approved", steps=len(steps)))
    return result, mode, run_id
