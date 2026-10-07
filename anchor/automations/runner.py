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

from .model import ApprovedPlan, Automation, AutomationError, AutomationStore
from .params import ParameterError, check_values, render, render_steps, templatize, templatize_steps
from .replay import ReplayPlanner


def _step_dict(step) -> dict:
    return asdict(step)


class NotesPlanner:
    """Gives the planner the user's notes about the task, on every call."""

    def __init__(self, planner, notes: list[str]):
        self.planner, self.notes = planner, list(notes)

    def __getattr__(self, name):
        return getattr(self.planner, name)

    def plan(self, *args, **kwargs):
        if self.notes:
            kwargs.setdefault("notes", self.notes)
        return self.planner.plan(*args, **kwargs)


def _with_notes(planner, notes: list[str]):
    return NotesPlanner(planner, notes) if notes else planner


def _unredone_steps(saved: list, broken_at: int, records: list) -> list[str]:
    """Saved steps, from the broken one on, with no successful step of the same action after the break."""
    from collections import Counter
    done = [r for r in records if r.status == "success"]
    after = Counter(r.step.action for r in done[broken_at:])
    missing = []
    for step in saved[broken_at:]:
        if after[step.action]:
            after[step.action] -= 1
        else:
            missing.append(f"{step.action} {step.description}")
    return missing


def _render_goals(goals, values):
    from dataclasses import replace
    return [replace(g, description=render(g.description, values)) for g in goals]


def _templatize_goals(goals, values):
    from dataclasses import replace
    return [replace(g, description=templatize(g.description, values)) for g in goals]


def run_automation(
    store: AutomationStore,
    name: str,
    page,
    executor: ActionExecutor,
    make_planner: Callable[[Automation], object],
    report: Optional[Callable[[str], None]] = print,
    relearn: bool = False,
    heal: bool = True,
    params: Optional[dict[str, str]] = None,
    confirm=None,
    **agent_options,
) -> tuple[AgentResult, str, str]:
    """
    Runs the automation; returns (result, mode, run id). mode: "learn" or "replay".
    params: the values of the automation's parameters for this run ({"nome": "Maria"}).
    confirm: whatever asks the user about sensitive actions (e.g. TerminalConfirmer); each
             decision is saved in the automation and not asked again.
    """
    automation = store.load(name)
    values = dict(params or {})
    try:
        check_values(automation.parameters, values)
    except ParameterError as exc:
        raise AutomationError(str(exc)) from exc
    approved = None if relearn else store.load_plan(name)
    say = report or (lambda _: None)
    notes = store.recent_notes(name)
    if confirm is not None:
        from .confirmations import AutomationConfirmer
        executor.confirmer = AutomationConfirmer(store, name, values, confirm, report=say)
    memory_before = set(executor.memory.entries) if executor.memory is not None else set()

    if approved is not None:
        mode = "replay"
        planner = ReplayPlanner(render_steps(approved.steps, values), _render_goals(approved.goals, values),
                                approved.language,
                                make_healer=(lambda: _with_notes(make_planner(automation), notes)) if heal else None,
                                report=say)
        say(t("auto.replaying", name=name, steps=len(approved.steps)))
    else:
        mode = "learn"
        planner = _with_notes(make_planner(automation), notes)
        say(t("auto.learning", name=name))

    # The caller opens the automation's link (page.goto(automation.url)) before running it.
    agent = Agent(page, planner, executor, report=report, **agent_options)
    result = agent.run(render(automation.request, values))

    healed = mode == "replay" and planner.broken and planner.healer is not None
    if healed and result.ok:
        missing = _unredone_steps(approved.steps, planner.broken_at, result.records)
        if missing:
            # The saved plan is a contract: every saved step that failed must have been redone
            # by a successful step of the same action. Otherwise the recovery is incomplete,
            # even if the model said nothing was left.
            result.status = "failed"
            result.message = t("auto.heal_incomplete", step=missing[0])
            say(t("agent.ended", message=result.message))
    if mode == "replay" and planner.broken and not result.ok:
        key = "auto.heal_failed" if healed else "auto.broken"
        result.status = "failed" if result.status == "success" else result.status
        result.message = t(key, reason=planner.broken_reason)
        say(t("agent.ended", message=result.message))

    run_id = store.save_run(name, {
        "version": __version__, "mode": mode, "status": result.status, "message": result.message,
        "healed": healed and result.ok,
        "denied": result.denied,
        "parameters": automation.parameters,     # the names only: the values may be personal data
        "steps": [{"action": r.step.action, "description": templatize(r.step.description, values),
                   "value": templatize(r.step.value, values), "status": r.status,
                   "resolved_by": r.resolved_by, "note": templatize(r.note, values), "score": r.score}
                  for r in result.records],
        "llm_calls": result.llm_calls, "replans": result.replans, "failures": result.failures,
        "interventions": result.interventions, "no_effect": result.no_effect, "seconds": result.seconds,
        "vision_checks": result.vision_checks, "vision_confirmed": result.vision_confirmed,
        "vision_seconds": result.vision_seconds, "user_wait_seconds": result.user_wait_seconds,
    })

    done = [r for r in result.records if r.status == "success"]
    if mode == "learn" and result.ok:
        steps = templatize_steps([r.step for r in done], values)
        used = {s.goal for s in steps if s.goal}
        goals = _templatize_goals([g for g in agent._goals.values() if g.id in used], values)
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=agent.language))
        say(t("auto.approved", steps=len(steps)))

    if healed and result.ok:
        failed = next((r for r in result.records if r.status != "success" and r.status != "skipped"), None)
        new_steps = [r for r in done][planner.broken_at:]
        steps = templatize_steps([r.step for r in done], values)
        used = {s.goal for s in steps if s.goal}
        goals = _templatize_goals([g for g in agent._goals.values() if g.id in used], values) or approved.goals
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=approved.language))
        record = store.add_recovery(name, {
            "run": run_id, "method": "replan",
            "failed_step": _step_dict(approved.steps[planner.broken_at]) if planner.broken_at < len(approved.steps) else None,
            "reason": templatize(failed.note if failed else planner.broken_reason, values),
            "replaced_by": [_step_dict(s) for s in templatize_steps([r.step for r in new_steps], values)],
            "effect_confirmed": agent.watcher is not None,
            "confidence": [{"step": templatize(r.step.description, values), "resolved_by": r.resolved_by,
                            "score": r.score} for r in new_steps],
            "previous_plan": {"steps": [_step_dict(s) for s in approved.steps],
                              "goals": [asdict(g) for g in approved.goals]},
        })
        say(t("auto.healed", number=record["number"], name=name))

    if mode == "replay" and executor.memory is not None:
        for key in sorted(set(executor.memory.entries) - memory_before):
            entry = executor.memory.entries[key]
            record = store.add_recovery(name, {
                "run": run_id, "method": "user", "memory_key": key,
                "step": {"action": entry.action, "description": templatize(entry.description, values)},
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
