"""
The agent loop: request → plan → step-by-step execution → replanning → end.

The LLM only plans. Each step is run by the ActionExecutor, which uses the
choice memory, the heuristic and, when the heuristic refuses, the user's
disambiguation. The agent goes back to the planner in three situations:

    1. the page changed (navigation, pop-up): asks for the remaining steps;
    2. a step failed: reports what was done and why it failed;
    3. the plan ended: asks whether anything is left; empty list = goal reached.

Three failures cancel the run, with a report to the user.

Two languages are in play: what the model reads (the history, the goals'
status, the failure reasons) follows the planner prompt's language; what the
user reads (the reports and the final message) follows the interface language.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from playwright.sync_api import Page

from anchor.engine.action_executor import ActionExecutor, ActionResult
from anchor.engine.element_resolver.resolver import accepts
from anchor.engine.element_resolver.tokenizer import (
    DESTRUCTIVE_N,
    STOPWORDS_N,
    normalize_tokens,
    tokenize,
)
from anchor.i18n import get_language, t
from anchor.planner import Plan, Step, page_elements, run_step
from anchor.planner.execute import clean_description, clean_value
from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, Reason, mt

from .effects import EffectWatcher, state_problem

# Stems of "pesquisar", "buscar", "procurar", "search", "find", "go": such a click
# with no button, right after filling in a field, becomes Enter.
SUBMIT_STEMS = {"pesquis", "busc", "procur", "search", "find", "go", "lupa"}


@dataclass
class StepRecord:
    step: Step
    status: str                  # success, not_found, ambiguous, error, skipped, loop, blocked...
    resolved_by: str = ""
    note: str = ""               # the reason, in the interface language


@dataclass
class AgentResult:
    status: str                  # "success" | "cancelled" | "failed"
    message: str
    records: list[StepRecord] = field(default_factory=list)
    llm_calls: int = 0
    replans: int = 0
    failures: int = 0
    interventions: int = 0       # steps in which the user chose the element
    no_effect: int = 0           # actions with no effect on the page
    goals_total: int = 0         # goals defined by the planner
    goals_done: int = 0          # goals fulfilled at the end
    suspicions: int = 0          # steps in which the expected text did not appear
    plan_failed: bool = False    # the initial plan could not be generated
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "success"


def step_key(step: Step) -> tuple:
    return (step.action, clean_description(step.description).lower(), step.value)


def describe_step(step: Step) -> str:
    value = f' = "{step.value}"' if step.value is not None else ""
    return f"{step.action} {step.description}{value}"


def failure_reason(result: ActionResult) -> Reason:
    """The failure reason, in words that help the planner try another way."""
    element = result.selected_element
    if element is not None and getattr(element, "obscured", False):
        return Reason("why.obscured")
    if result.status == "not_found":
        return Reason("why.not_found")
    if result.status == "ambiguous":
        return Reason("why.ambiguous")
    if result.status == "error":
        first_line = (result.error or "").strip().splitlines()[0][:120] if result.error else ""
        return Reason("why.error", detail=first_line) if first_line else Reason("why.error_plain")
    return Reason("why.status", status=result.status)


class Agent:
    """
    planner: any object with plan(request, url, page_elements, history) → Plan. Its
             "language" attribute (default "pt") sets the language the model reads.
    report: a function called with one line of text on each event (default: print).
    """

    def __init__(
        self,
        page: Page,
        planner,
        executor: ActionExecutor,
        max_failures: int = 3,
        max_steps: int = 25,
        verify_end: bool = True,
        max_end_checks: int = 2,
        max_repeats: int = 3,
        verify_effect: bool = True,
        report: Optional[Callable[[str], None]] = print,
    ):
        self.page = page
        self.planner = planner
        self.executor = executor
        self.max_failures = max_failures
        self.max_steps = max_steps
        self.verify_end = verify_end
        self.max_end_checks = max_end_checks
        self.max_repeats = max_repeats
        self.watcher = EffectWatcher(page) if verify_effect else None
        self.language = getattr(planner, "language", DEFAULT_PROMPT_LANGUAGE)
        self.report = report or (lambda _: None)

    # ------------------------------------------------------------------

    _VISIBLE_MESSAGES_JS = r"""() => [...document.querySelectorAll(
        '[role=alert],[role=status],[aria-live],.toast,.alert,.error,.message,.notification')]
        .filter(e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed')
        .map(e => (e.innerText || '').replace(/\s+/g, ' ').trim())
        .filter(t => t.length > 1 && t.length <= 160).slice(0, 5)"""

    def _context_lines(self) -> list[str]:
        """The goals' status and the visible messages, for the planner (not kept in the history)."""
        lines = []
        if self._goals:
            lines.append(mt("ctx.goals", self.language, goals="; ".join(
                f"{g.id} ({g.description}): {mt('goal.' + self._goal_status[g.id], self.language)}"
                for g in self._goals.values())))
        try:
            visible = self.page.evaluate(self._VISIBLE_MESSAGES_JS)
        except Exception:
            visible = []
        if visible:
            lines.append(mt("ctx.messages", self.language, messages=" | ".join(f'"{m}"' for m in visible)))
        return lines

    def _plan(self, request: str, history: list[str], result: AgentResult) -> Plan:
        elements = page_elements(self.executor.resolver, request=request, language=self.language)
        context = history + self._context_lines() if history else []
        extra = {"known_goals": set(self._goals)} if self._goals else {}
        plan = self.planner.plan(request, self.page.url, elements, context or None, **extra)
        for goal in getattr(plan, "goals", []) or []:
            if goal.id not in self._goals:
                self._goals[goal.id] = goal
                self._goal_status[goal.id] = "pending"
        result.goals_total = len(self._goals)
        result.llm_calls += 1
        result.tokens_in += plan.tokens_in
        result.tokens_out += plan.tokens_out
        return plan

    def _pending_goals(self) -> list[str]:
        """Goals that still prevent the end (dropped and replaced ones do not)."""
        return [f"{g.id} ({g.description})" for g in self._goals.values() if self._goal_status[g.id] == "pending"]

    def _supersede(self, failed_goal, queue) -> None:
        """After a failure, if the new plan has no steps for the goal, it was replaced."""
        if (failed_goal in self._goal_status and self._goal_status[failed_goal] == "pending"
                and not any(s.goal == failed_goal for s in queue)):
            self._goal_status[failed_goal] = "dropped"

    def _page_words(self) -> set[str]:
        try:
            text = self.page.inner_text("body")
        except Exception:
            return set()
        tokens = tokenize(text)
        return tokens | normalize_tokens(tokens)

    def _expected_missing(self, step: Step, words_before: set[str]) -> bool:
        """
        Did the expected text fail to appear after the step? (suspicion, not failure)
        Only new text counts: what was already on the page confirms nothing.
        """
        if not step.expect:
            return False
        want = normalize_tokens(tokenize(step.expect)) - STOPWORDS_N
        new = self._page_words() - words_before
        return bool(want) and len(want & new) / len(want) < 0.5

    def _finish(self, result: AgentResult, status: str, message: str, start: float) -> AgentResult:
        """message: already written in the interface language."""
        if status == "success" and self._pending_goals():
            status = "cancelled"
            message = t("end.pending_goals", goals=", ".join(self._pending_goals()))
        result.goals_done = sum(s == "done" for s in self._goal_status.values())
        result.status, result.message = status, message
        result.seconds = round(time.perf_counter() - start, 2)
        self.report(t("agent.done" if status == "success" else "agent.ended", message=message))
        return result

    # ------------------------------------------------------------------

    def _layer_count(self) -> int:
        """How many elements are in an open pop-up, dialog or menu."""
        return sum(1 for r in self.executor.resolver.records if r.get("layer"))

    @staticmethod
    def _destructive(text: str) -> bool:
        tokens = tokenize(text or "")
        return bool((tokens | normalize_tokens(tokens)) & DESTRUCTIVE_N)

    def _unrequested_destructive(self, request: str, step: Step) -> bool:
        """
        Does the step close, delete, remove, hide or cancel something the request did not
        mention? Closing a pop-up (notice, dialog) does not count: it is navigation.
        """
        if step.action != "click" or self._destructive(request):
            return False
        description = clean_description(step.description)
        if not self._destructive(description):
            return False
        status, found, _ = self.executor._resolve(description, "click")
        return not (found is not None and found.layer)

    def _execute(self, step: Step, last_fill) -> ActionResult:
        """Runs a step, with the Enter and field-reveal safety nets."""
        description = clean_description(step.description)

        # Enter instead of a search button that does not exist.
        if self._is_submit(step) and last_fill is not None:
            status, found, _ = self.executor._resolve(description, "click")
            record = next((r for r in self.executor.resolver.records
                           if found is not None and r["id"] == found.id), None)
            if status != "success" or (record is not None and accepts(record, "fill")):
                try:
                    last_fill.locator.press("Enter")
                    self.report(t("agent.enter"))
                    return ActionResult(status="success", action="press", description=step.description,
                                        selected_element=last_fill, resolved_by="enter_in_field")
                except Exception as exc:
                    return ActionResult(status="error", action="press", description=step.description, error=str(exc))

        # Enter on an element that is not a text field: goes to the last filled field.
        if step.action == "press" and (step.value or "").lower() == "enter" and last_fill is not None:
            status, found, _ = self.executor._resolve(description, "click")
            record = next((r for r in self.executor.resolver.records
                           if found is not None and r["id"] == found.id), None)
            if status != "success" or record is None or not accepts(record, "fill"):
                try:
                    last_fill.locator.press("Enter")
                    return ActionResult(status="success", action="press", description=step.description,
                                        selected_element=last_fill, resolved_by="enter_in_field")
                except Exception:
                    pass

        # A field that only appears after a click (e.g. the magnifier that opens the search).
        if step.action == "fill":
            status, _, _ = self.executor._resolve(description, "fill")
            if status == "not_found":
                revealed = self._reveal_and_fill(step, description)
                if revealed is not None:
                    return revealed

        return run_step(self.executor, step)

    def _reveal_and_fill(self, step: Step, description: str) -> Optional[ActionResult]:
        status, trigger, _ = self.executor._resolve(description, "click")
        if status != "success" or trigger is None:
            return None
        try:
            trigger.click()
            self.page.wait_for_timeout(400)
        except Exception:
            return None
        self.report(t("agent.revealed", description=description))

        status, target, _ = self.executor._resolve(description, "fill")
        if status != "success" or target is None:
            # The revealed field usually gets the focus (e.g. the field in a search pop-up).
            focused = self.page.locator(":focus")
            try:
                editable = focused.count() == 1 and focused.evaluate(
                    "e => e.matches('input, textarea, [contenteditable=\"\"], [contenteditable=true]') && !e.readOnly")
                er_id = focused.get_attribute("data-er-id") if editable else None
            except Exception:
                return None
            record = next((r for r in self.executor.resolver.records if r["id"] == er_id), None)
            if record is None:
                return None
            target = self.executor.resolver.to_match(record)
        try:
            target.fill(step.value or "")
        except Exception as exc:
            return ActionResult(status="error", action="fill", description=step.description, error=str(exc))
        return ActionResult(status="success", action="fill", description=step.description,
                            selected_element=target, resolved_by="revealed_field")

    def _verify(self, step: Step, outcome: ActionResult, before):
        """
        Checks the effect of a step that was run. Returns (problem, messages):
        None = effect ok; "no_effect" = nothing happened; "focus_only" = a click that only
        gives the focus; a Reason = what went wrong.
        """
        action = outcome.action if outcome.action in ("fill", "select", "check", "uncheck", "press") else step.action
        if action in ("hover", "extract_text"):
            return None, []
        effect = self.watcher.effect_since(before)
        errors = effect.errors
        others = [m for m in effect.new_messages if m not in errors]
        if errors:
            return Reason("why.error_message", message=errors[0]), others
        element = outcome.selected_element
        if action in ("fill", "select", "check", "uncheck") and element is not None:
            return state_problem(action, clean_value(step.value), element.locator), others
        if action == "click" and element is not None:
            record = next((r for r in self.executor.resolver.records if r["id"] == element.id), None) or {}
            if accepts(record, "check"):
                # Clicking a checkbox or option changes its state, not the page structure.
                was = bool((element.state or {}).get("checked"))
                try:
                    now = element.locator.is_checked()
                except Exception:
                    return None, others
                return (None if now != was or record.get("role") == "radio" and now else "no_effect"), others
            if accepts(record, "fill") or accepts(record, "select"):
                return "focus_only", others   # clicking a field or a list only gives the focus
        if action in ("click", "press") and not effect.changed:
            return "no_effect", others
        return None, others

    def _is_submit(self, step: Step) -> bool:
        return step.action == "click" and bool(tokenize(clean_description(step.description)) & SUBMIT_STEMS)

    def _replan(self, request, history, result, start, why):
        """Replans; returns the new queue, or an AgentResult if that is not possible."""
        self.report(t("agent.replanning", why=why))
        try:
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # invalid plan, connection, missing model...
            return self._finish(result, "failed", t("end.replan_failed", error=exc), start)
        result.replans += 1
        return queue

    def _fail(self, request, history, result, start, step, status, resolved_by, reason):
        """Records a failure and replans, or cancels after max_failures. reason: a Reason."""
        if step.goal in self._goal_status and status != "loop":
            self._goal_status[step.goal] = "pending"
        ui_reason = reason.render(get_language())
        result.failures += 1
        result.records.append(StepRecord(step, status, resolved_by, ui_reason))
        history.append(mt("hist.failed", self.language, step=describe_step(step), reason=reason.render(self.language)))
        self.report(t("agent.failed_step", reason=ui_reason))
        if result.failures >= self.max_failures:
            return self._finish(
                result, "cancelled",
                t("end.max_failures", max=self.max_failures, step=describe_step(step), reason=ui_reason),
                start,
            )
        queue = self._replan(request, history, result, start,
                             t("agent.why_attempt", n=result.failures + 1, max=self.max_failures))
        if isinstance(queue, AgentResult):
            return queue
        self._supersede(step.goal, queue)
        if not queue:
            return self._finish(result, "cancelled", t("end.no_other_way", reason=ui_reason), start)
        return queue

    def run(self, request: str) -> AgentResult:
        self._goals = {}
        self._goal_status = {}
        start = time.perf_counter()
        result = AgentResult(status="failed", message="")
        history: list[str] = []
        end_checks = 0
        done_count: dict[tuple, int] = {}
        last_done: Optional[tuple] = None   # last step performed successfully
        after_replan = False                # the current queue was just replanned
        last_fill = None                    # element of the last "fill", for the Enter
        blocked: set[tuple] = set()         # blocked destructive steps

        try:
            self.report(t("agent.planning"))
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # invalid plan, connection, missing model...
            result.plan_failed = True
            return self._finish(result, "failed", t("end.no_plan", error=exc), start)

        if not queue:
            return self._finish(result, "cancelled", t("end.cannot"), start)

        while True:
            # ---------------------------------------------------- end of the plan
            if not queue:
                if not self.verify_end:
                    return self._finish(result, "success", t("end.all_steps"), start)
                if end_checks >= self.max_end_checks:
                    return self._finish(result, "cancelled", t("end.end_checks"), start)
                end_checks += 1
                self.report(t("agent.checking_end"))
                try:
                    queue = list(self._plan(request, history, result).steps)
                except Exception as exc:
                    return self._finish(result, "failed", t("end.check_failed", error=exc), start)
                # Steps already done that the check proposes again: the model did not notice
                # they were done. Drop them; if nothing is left, the goal was reached.
                queue = [s for s in queue if step_key(s) not in done_count]
                if not queue:
                    return self._finish(result, "success", t("end.goal_reached"), start)
                result.replans += 1
                after_replan = True
                continue

            if len(result.records) >= self.max_steps:
                return self._finish(result, "failed", t("end.max_steps", max=self.max_steps), start)

            step = queue.pop(0)
            key = step_key(step)

            # ---------------------------------------------------- loop
            repeated_now = after_replan and key == last_done
            if repeated_now or done_count.get(key, 0) >= self.max_repeats:
                reason = (Reason("why.repeated_now") if repeated_now
                          else Reason("why.repeated", count=done_count[key]))
                self.report(f"  ↺ {describe_step(step)}")
                after_replan = False
                outcome = self._fail(request, history, result, start, step, "loop", "", reason)
                if isinstance(outcome, AgentResult):
                    return outcome
                queue, after_replan = outcome, True
                continue
            after_replan = False

            # ---------------------------------------------------- unrequested destructive action
            if self._unrequested_destructive(request, step):
                reason = Reason("why.destructive")
                self.report(t("agent.blocked", step=describe_step(step)))
                if key in blocked:
                    outcome = self._fail(request, history, result, start, step, "blocked", "", reason)
                    if isinstance(outcome, AgentResult):
                        return outcome
                    queue, after_replan = outcome, True
                    continue
                blocked.add(key)
                if self._goal_status.get(step.goal) == "pending" and not any(
                        r.status == "success" and r.step.goal == step.goal for r in result.records):
                    self._goal_status[step.goal] = "dropped"   # a goal that only had the blocked action
                result.records.append(StepRecord(step, "blocked", "", reason.render(get_language())))
                history.append(mt("hist.blocked", self.language, step=describe_step(step),
                                  reason=reason.render(self.language)))
                continue

            url_before = self.page.url
            self.report(f"  → {describe_step(step)}")

            before = self.watcher.snapshot() if self.watcher else None
            words_before = self._page_words() if (self.watcher and step.expect) else set()
            outcome = self._execute(step, last_fill)

            if outcome.resolved_by == "user":
                result.interventions += 1

            # ---------------------------------------------------- effect check
            messages: list[str] = []
            focus_only = False
            if outcome.status == "success" and self.watcher is not None:
                problem, messages = self._verify(step, outcome, before)
                if problem == "no_effect":
                    self.report(t("agent.retry_no_effect"))
                    before = self.watcher.snapshot()
                    outcome = self._execute(step, last_fill)
                    if outcome.status == "success":
                        problem, messages = self._verify(step, outcome, before)
                focus_only = problem == "focus_only"
                if focus_only:
                    problem = None
                if outcome.status == "success" and problem:
                    history.extend(mt("hist.message", self.language, message=m) for m in messages)
                    status = "no_effect" if problem == "no_effect" else "wrong_effect"
                    reason = Reason("why.no_effect") if problem == "no_effect" else problem
                    if outcome.resolved_by == "memory" and self.executor.memory is not None:
                        # The remembered choice no longer works: forget it.
                        self.executor.memory.forget(url_before, outcome.action, clean_description(step.description))
                    result.no_effect += problem == "no_effect"
                    outcome_q = self._fail(request, history, result, start, step, status,
                                           outcome.resolved_by, reason)
                    if isinstance(outcome_q, AgentResult):
                        return outcome_q
                    queue, after_replan = outcome_q, True
                    continue

            # ---------------------------------------------------- success
            if outcome.status == "success":
                result.records.append(StepRecord(step, "success", outcome.resolved_by))
                history.append(mt("hist.done", self.language, step=describe_step(step)))
                history.extend(mt("hist.message", self.language, message=m) for m in messages)
                if step.goal in self._goal_status and not (self.watcher is not None and focus_only):
                    # A click that only gives the focus does not fulfill the goal.
                    self._goal_status[step.goal] = "done"
                if self.watcher is not None and self._expected_missing(step, words_before):
                    result.suspicions += 1
                    result.records[-1].note = mt("why.expected_missing", get_language(), expect=step.expect)
                    history.append(mt("hist.suspicion", self.language, step=describe_step(step), expect=step.expect))
                done_count[key] = done_count.get(key, 0) + 1
                last_done = key
                if step.action == "fill" and outcome.selected_element is not None:
                    last_fill = outcome.selected_element

                layers_before = self._layer_count()
                if self.page.url != url_before:
                    self.page.wait_for_load_state()
                    why = t("agent.why_page")
                elif step.action == "fill":
                    # Suggestions that appear while typing are a normal effect of
                    # typing: they do not justify replanning.
                    why = ""
                else:
                    self.executor.resolver.index("interactive")
                    layers_after = self._layer_count()
                    why = (t("agent.why_popup_opened") if layers_after > layers_before
                           else t("agent.why_popup_closed") if layers_after < layers_before
                           else "")
                if why:
                    queue = self._replan(request, history, result, start, why)
                    if isinstance(queue, AgentResult):
                        return queue
                    after_replan = True
                continue

            # ---------------------------------------------------- skipped by the user
            if outcome.resolved_by == "user_skipped":
                result.records.append(StepRecord(step, "skipped", "user_skipped"))
                history.append(mt("hist.skipped", self.language, step=describe_step(step)))
                self.report(t("agent.skipped"))
                continue

            # ---------------------------------------------------- failure
            outcome_q = self._fail(request, history, result, start, step,
                                   outcome.status, outcome.resolved_by, failure_reason(outcome))
            if isinstance(outcome_q, AgentResult):
                return outcome_q
            queue, after_replan = outcome_q, True
