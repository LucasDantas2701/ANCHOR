"""
The three ablations of ANCHOR (the first two decided on 13/11/2026, the third on 19/11/2026, all before the
final run): each removes one of its parts,
on the same request sets and the same resilience benchmark, to measure what that part is worth.

  no_verify     without the effect check: after a step, the agent does not check that it had the expected
                effect (the agent's own verify_effect option, off). Everything else is ANCHOR.
  model_picks   with the element chosen by the model, in place of the Resolver: for each step, the model sees
                the page's numbered list of elements (the same list the model in control sees) and picks one;
                everything else (the barriers, the confirmations, the effect check, the replanning, the
                choice memory) is ANCHOR. Readings (extract_text and the like) still find their text with the
                Resolver, as the list has only the elements one can act on.
  no_safety     without the safety barriers: nothing is blocked or confirmed. Off: the agent's blocks before
                a step (an unrequested destructive action, an unrequested send, save, payment, print or
                account action, a file for the wrong field or the wrong file), the saved automation's guard
                (it refuses to act when an element changed and no one can be asked) and the refusal to type
                passwords; there is no confirmer either (the evaluation sets none). On, as the author decided
                (19/11/2026): the filter that keeps page text that looks like an instruction out of what the
                model reads, since it blocks and confirms nothing. Everything else is ANCHOR.

Besides them, one more condition of ANCHOR (decided on 19/11/2026): ANCHOR with the person in the loop,
simulated by an oracle that answers from the task's answer key (its allowed elements, or the step markers in
the resilience benchmark), so it adds what a person would, with nothing else changed:

  oracle        when ANCHOR asks which element (ambiguous or not found), it picks the candidate ANCHOR shows
                when exactly one of them is an allowed element; when none is, or more than one is, it says "none
                of these" (decided on 19/11/2026; the second case after the development run, where picking the
                first of two allowed candidates chose the wrong one for the step), and ANCHOR replans as it
                would with a person who recognised none or was not sure. When ANCHOR asks to confirm a
                sensitive action, it approves if the element is an allowed one and denies it if not. It does
                not log in (decided on 19/11/2026): a run that needs a login stops there, as without it. It
                counts its answers (the questions per task). The answer key holds the task's allowed elements,
                not each step's, so it never picks between two allowed candidates: it cannot tell which is
                this step's.

All of them live here, in the evaluation's code: no line of the engine changes, and with no ablation chosen, the
runners build ANCHOR exactly as before. Their runs are marked with their own executor name, so the tables
compare each one with ANCHOR as a separate system.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from unittest import mock

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor

ABLATIONS = ("no_verify", "model_picks", "no_safety")
CONDITIONS = ABLATIONS + ("oracle",)
EXECUTOR_NAME = {None: "anchor", "no_verify": "anchor_noverify", "model_picks": "anchor_modelpick",
                 "no_safety": "anchor_nosafety", "oracle": "anchor_oracle"}

PICK_SYSTEM = """Você escolhe, numa página, o elemento em que um passo deve agir. Você recebe o passo \
(a ação e a descrição do elemento) e a lista numerada dos elementos da página. Responda só com o número \
do elemento, sem texto antes ou depois, ou 0 se nenhum corresponder."""


def agent_options(ablation: str | None) -> dict:
    """The Agent's options for an ablation (nothing for ANCHOR as measured)."""
    return {"verify_effect": False} if ablation == "no_verify" else {}


class ModelPickExecutor(ActionExecutor):
    """ANCHOR's executor with one change: the element of each step is chosen by the model, from the page's
    numbered element list, instead of by the Resolver's scores and thresholds."""

    def __init__(self, page, client, model: str, **kwargs):
        super().__init__(page, **kwargs)
        self.client, self.model = client, model
        self.calls = self.tokens_in = self.tokens_out = 0

    def _resolve(self, description: str, resolver_action: str):
        if resolver_action == "extract":
            return super()._resolve(description, resolver_action)      # readings: see the module's note
        from eval.resilience.executors import LLM_SEED, numbered_elements
        lines, ids = numbered_elements(self.resolver)
        if not ids:
            return "not_found", None, []
        user = f'Passo: {resolver_action} "{description}"\n\nElementos:\n' + "\n".join(lines)
        response = self.client.chat.completions.create(
            model=self.model, temperature=0, seed=LLM_SEED,
            messages=[{"role": "system", "content": PICK_SYSTEM}, {"role": "user", "content": user}])
        self.calls += 1
        usage = getattr(response, "usage", None)
        self.tokens_in += getattr(usage, "prompt_tokens", 0) or 0
        self.tokens_out += getattr(usage, "completion_tokens", 0) or 0
        found = re.search(r"\d+", response.choices[0].message.content or "")
        number = int(found.group()) if found else 0
        if not 1 <= number <= len(ids):
            return "not_found", None, []
        record = next(r for r in self.resolver.records if r["id"] == ids[number - 1])
        match = self.resolver.to_match(record, score=1.0)
        return "success", match, [match]


class NoSafetyExecutor(ActionExecutor):
    """ANCHOR's executor with its barriers off: the guard, the password refusal and the confirmer stay unset,
    whatever the agent or the automation runner sets them to (they set attributes; these ignore them)."""

    guard = property(lambda self: None, lambda self, value: None)
    refuse_passwords = property(lambda self: False, lambda self, value: None)
    confirmer = property(lambda self: None, lambda self, value: None)


class NoSafetyAgent(Agent):
    """ANCHOR's agent with no block before a step: none of its checks finds a step to refuse."""

    def _unrequested_destructive(self, request, step) -> bool:
        return False

    def _unrequested_submit(self, request, step) -> str:
        return ""

    def _wrong_file(self, request, step) -> bool:
        return False

    def _wrong_field(self, request, step) -> bool:
        return False


ALLOWED_JS = """([id, selectors]) => {
    const e = document.querySelector(`[data-er-id="${id}"]`);
    return !!e && selectors.some(s => { try { return e.matches(s); } catch (_) { return false; } });
}"""


class OracleExecutor(ActionExecutor):
    """ANCHOR's executor with a simulated person who answers from the answer key (see the module's note)."""

    def __init__(self, page, allowed: list[str], **kwargs):
        super().__init__(page, **kwargs)
        self.allowed = list(allowed or [])
        self.questions = 0
        self.disambiguator = self       # ANCHOR asks only when someone can answer; the oracle is that someone

    def choose(self, request):          # never called: _ask_user answers directly (the Disambiguator protocol)
        raise NotImplementedError

    def notify(self, message: str) -> None:
        pass

    def is_allowed(self, match) -> bool:
        """Whether a candidate is one of the task's allowed elements, in the page or any of its frames."""
        from anchor.engine.frames import evaluate_all
        return any(evaluate_all(self.page, ALLOWED_JS, [getattr(match, "id", ""), self.allowed]))

    def _ask_user(self, description, action_name, reason, candidates):
        from anchor.engine.disambiguation import UserChoice
        self.questions += 1
        shown = self._choices_to_show(reason, candidates)
        allowed = [(number, match) for number, match in enumerate(shown, 1) if self.is_allowed(match)]
        if len(allowed) == 1:           # the answer key names this step's element only when one is allowed
            number, match = allowed[0]
            self._last_choice = UserChoice("candidate", number)
            return match
        self._last_choice = UserChoice("none")
        return None

    def _denied(self, action_name, description, match, resolved_by="memory"):
        from anchor.engine.action_executor.result import ActionResult
        from anchor.engine.sensitive import classify
        element = " ".join(x for x in (match.text, match.label, match.hint) if x).strip()
        if classify(action_name, description, element) is None:
            return None                 # not a sensitive action: ANCHOR asks nothing
        self.questions += 1
        if self.is_allowed(match):
            return None
        return ActionResult(status="denied", action=action_name, description=description,
                            selected_element=match, score=match.score, resolved_by=resolved_by)


def agent_class(ablation: str | None) -> type:
    """The Agent class for an ablation (ANCHOR's own, unless the barriers are off)."""
    return NoSafetyAgent if ablation == "no_safety" else Agent


@contextmanager
def building(ablation: str | None):
    """Within it, the automation runner (which builds its own Agent) builds the ablation's; with any other
    ablation, or none, nothing changes."""
    if ablation != "no_safety":
        yield
        return
    with mock.patch("anchor.automations.runner.Agent", NoSafetyAgent):
        yield


def make_executor(page, ablation: str | None, planner=None, allowed: list[str] | None = None, **kwargs) -> ActionExecutor:
    """ANCHOR's executor (as measured), or an ablation's or the oracle's, built the same way otherwise."""
    if ablation == "oracle":
        return OracleExecutor(page, allowed or [], **kwargs)
    if ablation == "model_picks":
        return ModelPickExecutor(page, planner.client, planner.model, **kwargs)
    if ablation == "no_safety":
        return NoSafetyExecutor(page, **kwargs)
    return ActionExecutor(page, **kwargs)
