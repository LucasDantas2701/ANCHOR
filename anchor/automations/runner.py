"""
Running a saved automation.

    learn  (no approved plan yet, or --relearn): the agent plans with the LLM; if the
           run succeeds, the steps that worked become the approved plan.
    replay (there is an approved plan): the plan is replayed without the LLM. When a
           saved step fails, the automation heals itself: the LLM plans the rest from
           the page as it is now and, if the run succeeds, the saved plan is corrected.
           Every recovery is recorded (what failed, the original step, what replaced it,
           how it was solved, whether the effect was confirmed, the confidence), and
           can be undone. Elements the user picks during a replay are recorded too.
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


def _step_dict(step) -> dict:
    return asdict(step)


def run_automation(
    store: AutomationStore,
    name: str,
    page,
    executor: ActionExecutor,
    make_planner: Callable[[Automation], object],
    report: Optional[Callable[[str], None]] = print,
    relearn: bool = False,
    heal: bool = True,
    **agent_options,
) -> tuple[AgentResult, str, str]:
    """Runs the automation; returns (result, mode, run id). mode: "learn" or "replay"."""
    automation = store.load(name)
    approved = None if relearn else store.load_plan(name)
    say = report or (lambda _: None)
    memory_before = set(executor.memory.entries) if executor.memory is not None else set()

    if approved is not None:
        mode = "replay"
        planner = ReplayPlanner(approved.steps, approved.goals, approved.language,
                                make_healer=(lambda: make_planner(automation)) if heal else None, report=say)
        say(t("auto.replaying", name=name, steps=len(approved.steps)))
    else:
        mode = "learn"
        planner = make_planner(automation)
        say(t("auto.learning", name=name))

    # The caller opens the automation's link (page.goto(automation.url)) before running it.
    agent = Agent(page, planner, executor, report=report, **agent_options)
    result = agent.run(automation.request)

    healed = mode == "replay" and planner.broken and planner.healer is not None
    if mode == "replay" and planner.broken and not result.ok:
        key = "auto.heal_failed" if healed else "auto.broken"
        result.status = "failed" if result.status == "success" else result.status
        result.message = t(key, reason=planner.broken_reason)
        say(t("agent.ended", message=result.message))

    run_id = store.save_run(name, {
        "version": __version__, "mode": mode, "status": result.status, "message": result.message,
        "healed": healed and result.ok,
        "steps": [{"action": r.step.action, "description": r.step.description, "value": r.step.value,
                   "status": r.status, "resolved_by": r.resolved_by, "note": r.note, "score": r.score}
                  for r in result.records],
        "llm_calls": result.llm_calls, "replans": result.replans, "failures": result.failures,
        "interventions": result.interventions, "no_effect": result.no_effect, "seconds": result.seconds,
    })

    done = [r for r in result.records if r.status == "success"]
    if mode == "learn" and result.ok:
        steps = [r.step for r in done]
        used = {s.goal for s in steps if s.goal}
        goals = [g for g in agent._goals.values() if g.id in used]
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=agent.language))
        say(t("auto.approved", steps=len(steps)))

    if healed and result.ok:
        failed = next((r for r in result.records if r.status != "success" and r.status != "skipped"), None)
        new_steps = [r for r in done][planner.broken_at:]
        steps = [r.step for r in done]
        used = {s.goal for s in steps if s.goal}
        goals = [g for g in agent._goals.values() if g.id in used] or approved.goals
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=approved.language))
        record = store.add_recovery(name, {
            "run": run_id, "method": "replan",
            "failed_step": _step_dict(approved.steps[planner.broken_at]) if planner.broken_at < len(approved.steps) else None,
            "reason": failed.note if failed else planner.broken_reason,
            "replaced_by": [_step_dict(r.step) for r in new_steps],
            "effect_confirmed": agent.watcher is not None,
            "confidence": [{"step": r.step.description, "resolved_by": r.resolved_by, "score": r.score} for r in new_steps],
            "previous_plan": {"steps": [_step_dict(s) for s in approved.steps],
                              "goals": [asdict(g) for g in approved.goals]},
        })
        say(t("auto.healed", number=record["number"], name=name))

    if mode == "replay" and executor.memory is not None:
        for key in sorted(set(executor.memory.entries) - memory_before):
            entry = executor.memory.entries[key]
            record = store.add_recovery(name, {
                "run": run_id, "method": "user", "memory_key": key,
                "step": {"action": entry.action, "description": entry.description},
                "effect_confirmed": agent.watcher is not None,
            })
            say(t("auto.user_recovery", number=record["number"], description=entry.description))
    return result, mode, run_id


def undo_recovery(store: AutomationStore, name: str, number: int, memory=None) -> dict:
    """
    Undoes a recovery. A plan correction ("replan") restores the plan from before it, which
    also undoes the plan corrections made after it. A user choice ("user") is forgotten
    from the choice memory, so the next run asks again.
    """
    records = store.recoveries(name)
    record = next((r for r in records if r["number"] == number), None)
    if record is None:
        raise ValueError(t("auto.no_recovery", number=number))
    if record["undone"]:
        raise ValueError(t("auto.already_undone", number=number))
    if record["method"] == "replan":
        from anchor.planner import Goal, Step
        previous = record["previous_plan"]
        current = store.load_plan(name)
        store.save_plan(name, ApprovedPlan(steps=[Step(**s) for s in previous["steps"]],
                                           goals=[Goal(**g) for g in previous["goals"]],
                                           language=current.language if current else "pt",
                                           source_run=f"undo of recovery {number}"))
        later = {r["number"] for r in records if r["method"] == "replan" and r["number"] >= number and not r["undone"]}
        store.mark_undone(name, later)
    else:
        if memory is not None:
            memory.forget_key(record["memory_key"])
        store.mark_undone(name, {number})
    return record
