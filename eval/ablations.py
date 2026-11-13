"""
The two ablations of ANCHOR (decided on 13/11/2026, before the final run): each removes one of its parts,
on the same request sets and the same resilience benchmark, to measure what that part is worth.

  no_verify     without the effect check: after a step, the agent does not check that it had the expected
                effect (the agent's own verify_effect option, off). Everything else is ANCHOR.
  model_picks   with the element chosen by the model, in place of the Resolver: for each step, the model sees
                the page's numbered list of elements (the same list the model in control sees) and picks one;
                everything else (the barriers, the confirmations, the effect check, the replanning, the
                choice memory) is ANCHOR. Readings (extract_text and the like) still find their text with the
                Resolver, as the list has only the elements one can act on.

Both live here, in the evaluation's code: no line of the engine changes, and with no ablation chosen, the
runners build ANCHOR exactly as before. Their runs are marked with their own executor name, so the tables
compare each one with ANCHOR as a separate system.
"""
from __future__ import annotations

import re

from anchor.engine.action_executor import ActionExecutor

ABLATIONS = ("no_verify", "model_picks")
EXECUTOR_NAME = {None: "anchor", "no_verify": "anchor_noverify", "model_picks": "anchor_modelpick"}

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


def make_executor(page, ablation: str | None, planner=None, **kwargs) -> ActionExecutor:
    """ANCHOR's executor (as measured), or the model-picks one, built the same way otherwise."""
    if ablation == "model_picks":
        return ModelPickExecutor(page, planner.client, planner.model, **kwargs)
    return ActionExecutor(page, **kwargs)
