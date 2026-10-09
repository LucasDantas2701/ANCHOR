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

import re
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
from anchor.planner import Plan, PlanError, Step, check_request, page_elements, run_step
from anchor.planner.execute import clean_description, clean_value
from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, Reason, mt
from anchor.planner.untrusted import looks_like_instruction

from .effects import EffectWatcher, state_problem
from .login import password_field, request_has_password, wants_login

# Stems of "pesquisar", "buscar", "procurar", "search", "find", "go": such a click
# with no button, right after filling in a field, becomes Enter.
SUBMIT_STEMS = {"pesquis", "busc", "procur", "search", "find", "go", "lupa"}


@dataclass
class StepRecord:
    step: Step
    status: str                  # success, not_found, ambiguous, error, skipped, loop, blocked...
    resolved_by: str = ""
    note: str = ""               # the reason, in the interface language
    score: Optional[float] = None    # confidence: heuristic score, or memory similarity
    element: str = ""                # the name of the element acted on (for the records and diagnosis)
    # For boxes and lists: the element itself and the state it was left in, to notice when a
    # later step undoes it (checking "CLT" unchecks "PJ"). Not saved anywhere.
    handle: object = field(default=None, repr=False, compare=False)
    state: tuple = field(default=(), repr=False, compare=False)


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
    denied: bool = False         # the user denied a sensitive action
    vision_checks: int = 0       # questions asked about screenshots (layer 4)
    vision_confirmed: int = 0    # doubted steps the screenshot confirmed
    vision_seconds: float = 0.0  # time spent on those questions
    user_wait_seconds: float = 0.0   # time waiting for the user (disambiguation, confirmations, logins), within seconds
    logins: int = 0              # times the user logged in by hand when the task needed it
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


def user_text(exc: Exception) -> str:
    """An error for the user, in the interface language (plan errors are written for the model)."""
    return exc.user_text() if isinstance(exc, PlanError) else str(exc)


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
        vision=None,
        login=None,
    ):
        """
        login: whatever asks the user to log in by hand when the task needs it (e.g.
               TerminalLoginWaiter). The agent never types a password; without it, a task that
               needs a login stops.
        """
        self.login = login
        self.page = page
        self.planner = planner
        self.executor = executor
        self.max_failures = max_failures
        self.max_steps = max_steps
        self.verify_end = verify_end
        self.max_end_checks = max_end_checks
        self.max_repeats = max_repeats
        self.watcher = EffectWatcher(page) if verify_effect else None
        executor.refuse_passwords = True     # credentials never go through the model
        # Layer 4: asks a model about screenshots when the other checks doubt a step (see vision.py).
        self.vision = vision if verify_effect else None
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
            lines.append(mt("ctx.messages", self.language,
                            messages=" | ".join(f'"{m}"' for m in self._safe_messages(visible))))
        return lines

    def _plan(self, request: str, history: list[str], result: AgentResult) -> Plan:
        elements = page_elements(self.executor.resolver, request=request, language=self.language)
        context = history + self._context_lines() if history else []
        extra = {"known_goals": set(self._goals)} if self._goals else {}
        plan = self.planner.plan(request, self.page.url, elements, context or None, **extra)
        if getattr(plan, "incomplete", ""):
            self.report(t("agent.partial_plan"))
        for goal in getattr(plan, "goals", []) or []:
            if goal.id not in self._goals:
                self._goals[goal.id] = goal
                self._goal_status[goal.id] = "pending"
        result.goals_total = len(self._goals)
        if self._uses_llm():
            result.llm_calls += 1
        result.tokens_in += plan.tokens_in
        result.tokens_out += plan.tokens_out
        return plan

    def _uncovered(self, request: str, result: "AgentResult"):
        """
        Do the steps that were actually performed cover the request? The same check the
        initial plan goes through (conclusive verbs in a click or key press, the request's
        data in some step), but on what was done, not on what was planned. Returns None if
        they do, or the reason (model language, interface language) if they do not.
        """
        done = [r.step for r in result.records if r.status == "success"]
        try:
            check_request(done, [], request, self.language)
            return None
        except PlanError as model_error:
            try:
                check_request(done, [], request, get_language())
            except PlanError as ui_error:
                return str(model_error), str(ui_error)
            return str(model_error), str(model_error)

    def _safe_messages(self, messages: list[str]) -> list[str]:
        """Page messages that look like instructions to the assistant are left out (page content is data)."""
        return [mt("summary.suspicious", self.language) if looks_like_instruction(m) else m for m in messages]

    _STATE_REASONS = ("why.field_value", "why.list_value", "why.not_checked", "why.still_checked")

    def _remember_state(self, record: StepRecord, step: Step, chosen) -> None:
        """Keeps the element and the state a box or list was left in (see StepRecord.handle)."""
        if self.watcher is None or chosen is None or step.action not in ("select", "check", "uncheck", "click"):
            return
        try:
            handle = chosen.locator.element_handle(timeout=300)
            if step.action == "select":
                record.state = ("select", clean_value(step.value) if step.value else step.value)
            elif step.action in ("check", "uncheck"):
                record.state = (step.action, None)
            elif handle.evaluate("e => e.type === 'checkbox' || e.type === 'radio'"):
                record.state = ("check" if handle.is_checked() else "uncheck", None)
            else:
                return
            record.handle = handle
        except Exception:
            record.state, record.handle = (), None

    def _undone_by_this_step(self, result: AgentResult, outcome: ActionResult, request: str,
                             step: Step) -> Optional[StepRecord]:
        """
        An earlier box or list, verified before, that this step left in another state, when the
        earlier step was asked for and this one is not ("PJ" then "CLT", for "contrato PJ").
        Undoing a step the request did not ask for is a correction; and when both are in the
        request ("Register the employee ... contractor", with "Employee" and "Contractor"
        options), there is no telling which is right here: the final checks decide.
        """
        if self.watcher is None:
            return None
        asked = self._object(request)
        chosen = outcome.selected_element
        now = self._object(step.description + " " + (getattr(chosen, "text", "") or "") + " "
                           + (getattr(chosen, "label", "") or ""))
        for record in reversed(result.records):
            if record.status != "success" or record.handle is None:
                continue
            if state_problem(record.state[0], record.state[1], record.handle) is None:
                continue
            before = self._object(record.step.description + " " + record.element)
            if before & asked and not now & asked:
                return record                # a requested state undone by an unrequested step
        return None

    def _confirmed_by_screenshot(self, step: Step, problem, shot_before) -> bool:
        """
        Layer 4: does a screenshot confirm a step the other checks doubted? Only a state that
        did not match, or a click with no visible effect in the code. An error message on the
        page is never overruled.
        """
        if self.vision is None:
            return False
        if problem == "no_effect" and shot_before is not None:
            answer = self.vision.changed(shot_before, self.page, describe_step(step))
        elif isinstance(problem, Reason) and problem.key in self._STATE_REASONS:
            value = clean_value(step.value) if step.value else step.value
            answer = self.vision.shows_state(self.page, step.action, clean_description(step.description), value)
        else:
            return False
        if answer:
            self.report(t("agent.vision_confirmed"))
        return bool(answer)

    def _text_on_screenshot(self, step: Step, result: "AgentResult") -> bool:
        """Layer 4 for a suspicion: does the screenshot show the expected text the code did not?"""
        if self.vision is None or not step.expect:
            return False
        if self.vision.shows_text(self.page, step.expect):
            result.vision_confirmed += 1
            self.report(t("agent.vision_confirmed"))
            return True
        return False

    def _uses_llm(self) -> bool:
        """False while a saved plan is replayed without the LLM (for the messages and the metrics)."""
        return getattr(self.planner, "uses_llm", True)

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
        if self.vision is not None:
            result.vision_checks = self.vision.checks
            result.vision_seconds = round(self.vision.seconds, 2)
        if status == "success" and self._pending_goals():
            status = "cancelled"
            message = t("end.pending_goals", goals=", ".join(self._pending_goals()))
        result.goals_done = sum(s == "done" for s in self._goal_status.values())
        result.status, result.message = status, message
        result.seconds = round(time.perf_counter() - start, 2)
        result.user_wait_seconds = round(getattr(self.executor, "user_wait_s", 0.0) - self._wait_at_start, 2)
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

    @staticmethod
    def _object(text: str) -> set[str]:
        """What a text is about: its words, without verbs, stop words and structural words."""
        from anchor.engine.element_resolver.tokenizer import (
            ACTION_WORDS_N,
            STOPWORDS_N,
            STRUCTURAL_WORDS_N,
        )
        return normalize_tokens(tokenize(text or "")) - ACTION_WORDS_N - STOPWORDS_N - STRUCTURAL_WORDS_N

    _TOTALITY = {"tudo", "todos", "todas", "all", "everything", "everyone", "everybody"}

    def _unrequested_destructive(self, request: str, step: Step) -> bool:
        """
        Does the step close, delete, remove, hide or cancel something the request did not ask
        for? Closing a pop-up (notice, dialog) does not count: it is navigation. When the
        request does ask to delete or cancel, the step must be about what the request names
        ("Excluir (Bruno Lima)" for "exclua o Bruno Lima", not "Excluir tudo"), and it may act
        on everything only if the request says so.
        """
        if step.action != "click":
            return False
        description = clean_description(step.description)
        if not self._destructive(description):
            return False
        status, found, _ = self.executor._resolve(description, "click")
        if found is not None and found.layer:
            return False
        if not self._destructive(request):
            return True
        totality = {w for w in self._TOTALITY}
        step_words = {w.lower() for w in re.findall(r"\w+", description + " " + (getattr(found, "text", "") or ""))}
        request_words = {w.lower() for w in re.findall(r"\w+", request)}
        if step_words & totality:
            return not request_words & totality      # "delete everything" only if the request says so
        about = self._object(description)
        return bool(about) and not about & self._object(request)

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

    def _wait_login(self, result: AgentResult, history: list[str]) -> Optional[bool]:
        """
        Asks the user to log in by hand. None: no one to ask (the caller goes on as before);
        True: logged in (or the password field was filled in by the user); False: given up.
        """
        if self.login is None:
            return None
        for attempt in range(3):
            waited = time.perf_counter()
            done = self.login.wait(self.page.url)
            self.executor.user_wait_s = getattr(self.executor, "user_wait_s", 0.0) + time.perf_counter() - waited
            if not done:
                return False
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            field = password_field(self.page)
            if field is None or field.get("filled"):
                result.logins += 1
                history.append(mt("hist.logged_in", self.language))
                return True
            self.report(t("login.still"))
        return False

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
        self.report(t("agent.replanning" if self._uses_llm() else "agent.continuing", why=why))
        try:
            queue = list(self._plan(request, history, result).steps)
        except Exception as exc:  # invalid plan, connection, missing model...
            return self._finish(result, "failed", t("end.replan_failed", error=user_text(exc)), start)
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
        # The language the model reads: the planner may choose it per request ("auto").
        if hasattr(self.planner, "language_for"):
            self.language = self.planner.language_for(request)
        if self.vision is not None:
            self.vision.checks, self.vision.seconds, self.vision.language = 0, 0.0, self.language
        # The executor may serve several runs (a spreadsheet): count only this run's wait.
        self._wait_at_start = getattr(self.executor, "user_wait_s", 0.0)
        self._goals = {}
        self._goal_status = {}
        start = time.perf_counter()
        result = AgentResult(status="failed", message="")
        history: list[str] = []
        end_checks = 0
        coverage_warned = False             # the "request not fulfilled" warning was given
        done_count: dict[tuple, int] = {}
        last_done: Optional[tuple] = None   # last step performed successfully
        after_replan = False                # the current queue was just replanned
        last_fill = None                    # element of the last "fill", for the Enter
        blocked: set[tuple] = set()         # blocked destructive steps

        # A password in the request would reach the model: refused before anything is sent.
        if request_has_password(request):
            return self._finish(result, "failed", t("end.password_in_request"), start)
        # The request asks to log in, and the page shows a login: the user does it.
        if wants_login(request) and password_field(self.page) is not None:
            if self._wait_login(result, history) is False:
                return self._finish(result, "cancelled", t("end.login_needed"), start)

        queue, plan_error = [], None
        for _ in range(2):
            try:
                self.report(t("agent.planning" if self._uses_llm() else "agent.replaying"))
                queue, plan_error = list(self._plan(request, history, result).steps), None
            except Exception as exc:  # invalid plan, connection, missing model...
                queue, plan_error = [], exc
            # Nothing can be planned on a page that asks for a login: the task is behind it.
            if queue or password_field(self.page) is None or self._wait_login(result, history) is not True:
                break
        if plan_error is not None:
            result.plan_failed = True
            return self._finish(result, "failed", t("end.no_plan", error=user_text(plan_error)), start)

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
                self.report(t("agent.checking_end" if self._uses_llm() else "agent.checking_end_replay"))
                try:
                    queue = list(self._plan(request, history, result).steps)
                except Exception as exc:
                    return self._finish(result, "failed", t("end.check_failed", error=user_text(exc)), start)
                # Steps already done that the check proposes again: the model did not notice
                # they were done. Drop them; if nothing is left, the goal was reached.
                queue = [s for s in queue if step_key(s) not in done_count]
                if not queue:
                    # The model says nothing is left: check it against what was really done.
                    missing = self._uncovered(request, result)
                    if missing is None:
                        return self._finish(result, "success", t("end.goal_reached"), start)
                    model_reason, ui_reason = missing
                    if coverage_warned:
                        return self._finish(result, "cancelled", t("end.not_fulfilled", reason=ui_reason), start)
                    # Warn the model once. The warning gives it two more end checks: one to
                    # propose the missing steps, one to confirm the end.
                    coverage_warned = True
                    end_checks = min(end_checks, max(0, self.max_end_checks - 2))
                    history.append(mt("hist.not_fulfilled", self.language, reason=model_reason))
                    self.report(t("agent.not_fulfilled", reason=ui_reason))
                    continue
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
            shot_before = (self.vision.capture(self.page)
                           if self.vision is not None and step.action in ("click", "press") else None)
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
                if outcome.status == "success" and problem and self._confirmed_by_screenshot(step, problem, shot_before):
                    result.vision_confirmed += 1
                    problem = None
                if outcome.status == "success" and not problem:
                    undone = self._undone_by_this_step(result, outcome, request, step)
                    if undone is not None:
                        problem = Reason("why.undid", step=describe_step(undone.step))
                if outcome.status == "success" and problem:
                    history.extend(mt("hist.message", self.language, message=m) for m in self._safe_messages(messages))
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
                chosen = outcome.selected_element
                result.records.append(StepRecord(step, "success", outcome.resolved_by, score=(
                    outcome.score if outcome.score is not None else getattr(outcome, "similarity", None)),
                    element=" ".join(x for x in (getattr(chosen, "text", ""), getattr(chosen, "label", "")) if x)[:80]
                    if chosen is not None else ""))
                self._remember_state(result.records[-1], step, chosen)
                history.append(mt("hist.done", self.language, step=describe_step(step)))
                history.extend(mt("hist.message", self.language, message=m) for m in self._safe_messages(messages))
                if step.goal in self._goal_status and not (self.watcher is not None and focus_only):
                    # A click that only gives the focus does not fulfill the goal.
                    self._goal_status[step.goal] = "done"
                if (self.watcher is not None and self._expected_missing(step, words_before)
                        and not self._text_on_screenshot(step, result)):
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

            # ---------------------------------------------------- a password field
            if outcome.status == "credential":
                result.records.append(StepRecord(step, "credential", outcome.resolved_by))
                if self._wait_login(result, history) is not True:
                    return self._finish(result, "cancelled", t("end.login_needed"), start)
                queue = self._replan(request, history, result, start, t("agent.after_login"))
                if isinstance(queue, AgentResult):
                    return queue
                after_replan = True
                continue

            # ---------------------------------------------------- sensitive action denied
            if outcome.status == "denied":
                result.records.append(StepRecord(step, "denied", outcome.resolved_by))
                result.denied = True
                # No replanning: the model could look for another way to do what was denied.
                return self._finish(result, "cancelled", t("end.denied", step=describe_step(step)), start)

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
