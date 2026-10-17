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


def _about(text: str) -> set[str]:
    """What a step is about: its words, without verbs, stop words and structural words."""
    from anchor.engine.element_resolver.tokenizer import (
        ACTION_WORDS_N,
        STOPWORDS_N,
        STRUCTURAL_WORDS_N,
        normalize_tokens,
        tokenize,
    )
    return normalize_tokens(tokenize(text or "")) - ACTION_WORDS_N - STOPWORDS_N - STRUCTURAL_WORDS_N


def _acts(text: str) -> set[str]:
    """The action verbs in a step (add, delete, continue...), leaving out the ones that only navigate."""
    from anchor.engine.element_resolver.tokenizer import ACTION_WORDS_N, normalize_tokens, tokenize
    navigate = normalize_tokens(tokenize("open abrir view ver show mostrar exibir display go ir acessar access visit visitar"))
    return (normalize_tokens(tokenize(text or "")) & ACTION_WORDS_N) - navigate


def _closeness(step, description: str, value, element: str = "") -> float:
    """How much a step (its description, value and element) is about a saved step's thing: 1 = same
    value or all its words."""
    if step.value and value and step.value.strip().lower() == str(value).strip().lower():
        return 1.0
    # A saved step that only goes somewhere ("shopping cart link") is not redone by one that does
    # something ("Adicionar ao carrinho depois", "Continuar"): both share "cart", not the act.
    # The resilience benchmark's level 5 lured the model's repair into "add to cart later".
    if not _acts(step.description) and (_acts(description) | _acts(element)):
        return 0.0
    wanted = _about(step.description)
    if not wanted:
        return 1.0
    return len(wanted & (_about(description) | _about(element))) / len(wanted)


def _recovery_guard(planner, saved: list):
    """
    During a recovery, a step that acts (add, delete, continue...) must be the redo of a saved step
    still to redo, one that acts too, about the same thing: checked once the element is found and
    before acting, so a lure ("Adicionar ao carrinho depois") is never clicked. Steps that only go
    somewhere or prepare (close, open, show more) are left to the contract checked at the end.
    """
    clicks = ("click", "check", "uncheck")     # clicking a box is checking it

    def guard(action: str, description: str, match) -> Optional[str]:
        if not getattr(planner, "broken", False) or action not in clicks:
            return None          # the saved plan itself before any break; fields keep the contract (by value)
        element = " ".join(x for x in (getattr(match, "text", ""), getattr(match, "label", "")) if x)[:80]
        if not (_acts(description) | _acts(element)):
            return None
        for step in saved[planner.broken_at:]:
            if step.action in clicks and _acts(step.description) and _closeness(step, description, None, element) >= 0.5:
                return None
        return t("auto.recovery_acts", step=description, element=element or description)

    return guard


def _unredone_steps(saved: list, broken_at: int, records: list) -> list[str]:
    """
    Saved steps, from the broken one on, not redone after the break. Each must be matched by a
    different successful step of the same action about the same thing: the same value (a field
    or list renamed, "Nome" → "Funcionário", is filled with the same value), or a description (or
    element acted on) with at least half of the saved step's content words, the closest one first.
    "Accept cookies" does not redo "open the cart", and adding the laptop does not redo adding the
    headphones.
    """
    done = [r for r in records if r.status == "success"][broken_at:]
    used: set[int] = set()
    missing = []

    def closeness(step, record) -> float:
        return _closeness(step, record.step.description, record.step.value, getattr(record, "element", ""))

    for step in saved[broken_at:]:
        options = [(closeness(step, r), -i, i) for i, r in enumerate(done) if i not in used and r.step.action == step.action]
        best = max(options, default=None)
        match = best[2] if best is not None and best[0] >= 0.5 else None
        if match is None:
            missing.append(f"{step.action} {step.description}")
        else:
            used.add(match)
    return missing


class _NoOneToAsk:
    """
    An unattended run asks no one: a sensitive action not approved before is refused, and the refusal
    is NOT saved (an unattended run changes nothing in the automation; the next run with someone
    present asks again).
    """

    def confirm(self, request):
        from anchor.engine.sensitive import Decision
        return Decision(False, save=False)


def _element_key(text: str) -> str:
    return " ".join((text or "").lower().split())


def _proof_guard(proven: dict, values: dict):
    """Acts only on the element the proving run acted on for that step; anything else is a change."""
    expected = {render(k, values): render(v, values) for k, v in proven.items()}

    def guard(action: str, description: str, match) -> Optional[str]:
        key = f"{action}|{description}"
        if key not in expected:
            return t("auto.changed_step", step=description)
        found = " ".join(x for x in (getattr(match, "text", ""), getattr(match, "label", "")) if x)[:80]
        if _element_key(found) != _element_key(expected[key]):
            return t("auto.changed_element", step=description, expected=expected[key], found=found)
        return None

    return guard


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
    unattended: bool = False,
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
    if unattended:
        # Only a proven plan (done with someone present, with no recovery) runs with no one there,
        # and nothing may change: no repair by the model, no tie-break, no new sensitive action, no
        # waiting for a login, and each step acts only on the element of the proving run.
        if relearn or approved is None or not approved.proven_run:
            raise AutomationError(t("auto.not_proven", name=name))
        heal = False
        if confirm is not None:
            confirm = _NoOneToAsk()
        from anchor.agent.login import TerminalLoginWaiter
        agent_options["login"] = TerminalLoginWaiter(interactive=False)
        saved_disambiguator, executor.disambiguator = executor.disambiguator, None
        executor.guard = _proof_guard(approved.proven_elements, values)
        agent_options["max_failures"] = 1      # nothing is repaired: no second attempt
        if report is not None:                  # the run's own "Stopped" line is said once, at the end
            ended = t("agent.ended", message="")
            report = (lambda say_it: lambda line: None if line.startswith(ended) else say_it(line))(report)
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
    agent_options.setdefault("output_dir", store.folder(name) / "output")
    if mode == "replay" and heal and not unattended:
        executor.guard = _recovery_guard(planner, render_steps(approved.steps, values))
    agent = Agent(page, planner, executor, report=report, **agent_options)
    try:
        result = agent.run(render(automation.request, values))
    finally:
        executor.guard = None
        if unattended:
            executor.disambiguator = saved_disambiguator
    agent.close_opened_tabs()            # the next row starts from the automation's own tab

    healed = mode == "replay" and planner.broken and planner.healer is not None
    if healed and result.ok:
        missing = _unredone_steps(render_steps(approved.steps, values), planner.broken_at, result.records)
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
        if not unattended:
            say(t("agent.ended", message=result.message))
    if unattended and not result.ok:
        # The guard's own reason (the element that differs from the proving run) says the most.
        changed = next((r.note for r in result.records if r.status == "changed" and r.note), None)
        if changed is None and result.denied:
            step = next((r.step for r in result.records if r.status == "denied"), None)
            changed = t("auto.unattended_sensitive", step=f"{step.action} {step.description}" if step else "")
        result.message = t("auto.unattended_stopped", reason=changed or result.message)
        say(t("agent.ended", message=result.message))

    run_id = store.save_run(name, {
        "version": __version__, "mode": mode, "status": result.status, "message": result.message,
        "healed": healed and result.ok, "unattended": unattended,
        "denied": result.denied,
        "parameters": automation.parameters,     # the names only: the values may be personal data
        "steps": [{"action": r.step.action, "description": templatize(r.step.description, values),
                   "value": templatize(r.step.value, values), "status": r.status,
                   "resolved_by": r.resolved_by, "note": templatize(r.note, values), "score": r.score,
                   "element": templatize(getattr(r, "element", "") or "", values)}
                  for r in result.records],
        "llm_calls": result.llm_calls, "replans": result.replans, "failures": result.failures,
        "interventions": result.interventions, "no_effect": result.no_effect, "seconds": result.seconds,
        "vision_checks": result.vision_checks, "vision_confirmed": result.vision_confirmed,
        "vision_seconds": result.vision_seconds, "user_wait_seconds": result.user_wait_seconds,
        # The files written (extracted tables and lists); not the text read, which may be personal data.
        "outputs": [e["path"] for e in result.extractions if e.get("path")],
    })

    done = [r for r in result.records if r.status == "success"]
    # A run with someone present that did the plan with no recovery proves it (the elements it acted
    # on are what an unattended run may act on).
    chose = executor.memory is not None and bool(set(executor.memory.entries) - memory_before)
    proof = {}
    if result.ok and not unattended and not healed and (mode == "learn" or not chose):
        proof = {f"{r.step.action}|{templatize(r.step.description, values)}": templatize(getattr(r, "element", "") or "", values)
                 for r in done}
    if mode == "learn" and result.ok:
        steps = templatize_steps([r.step for r in done], values)
        used = {s.goal for s in steps if s.goal}
        goals = _templatize_goals([g for g in agent._goals.values() if g.id in used], values)
        store.save_plan(name, ApprovedPlan(steps=steps, goals=goals, source_run=run_id, language=agent.language,
                                           proven_run=run_id if proof else "", proven_elements=proof))
        say(t("auto.approved", steps=len(steps)))
        if proof:
            say(t("auto.proven", name=name))
    elif mode == "replay" and proof and approved.proven_run == "":
        approved.proven_run, approved.proven_elements = run_id, proof
        store.save_plan(name, approved)
        say(t("auto.proven", name=name))

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
