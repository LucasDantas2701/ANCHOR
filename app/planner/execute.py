"""Executa um plano com o ActionExecutor, passo a passo."""

from __future__ import annotations

import re

from app.engine.action_executor import ActionExecutor, ActionResult
from app.engine.disambiguation.describe import KIND

from .plan import Plan, Step

# Rótulos de tipo com várias palavras que o resumo da página usa ("Campo de texto",
# "Caixa de marcação"...). Os modelos tendem a copiá-los na descrição, e palavras
# como "texto" casam com todos os campos da página. Os de uma palavra ("Botão",
# "Link") ficam: ajudam a heurística.
_MULTIWORD_KINDS = sorted({k for k in KIND.values() if " " in k}, key=len, reverse=True)
_KIND_RE = re.compile(r"^(?:" + "|".join(re.escape(k) for k in _MULTIWORD_KINDS) + r")\s+", re.IGNORECASE)
_QUOTES_RE = re.compile(r"[\"“”]")
_POPUP_RE = re.compile(r"\s*\[pop-up\]", re.IGNORECASE)


def clean_description(text: str) -> str:
    """Tira rótulos de tipo e a marca [pop-up] copiados do resumo da página, e aspas."""
    cleaned = _QUOTES_RE.sub("", _KIND_RE.sub("", _POPUP_RE.sub("", text).strip())).strip()
    return cleaned or text


def run_step(executor: ActionExecutor, step: Step) -> ActionResult:
    a, d, v = step.action, clean_description(step.description), step.value
    if a == "fill":
        return executor.fill(d, v)
    if a == "select":
        result = executor.select(d, label=v)
        # "select" que não deu certo pode ser um botão de opção ou uma caixa de
        # marcação descrita como "opção": tenta marcar e só usa se funcionar.
        if result.status != "success":
            checked = executor.check(d)
            if checked.status == "success":
                return checked
        return result
    if a == "press":
        return executor.press(d, key=v)
    return getattr(executor, a)(d)  # click, hover, check, uncheck, extract_text


def run_plan(executor: ActionExecutor, plan: Plan, stop_on_failure: bool = True) -> list[tuple[Step, ActionResult]]:
    results = []
    for step in plan.steps:
        result = run_step(executor, step)
        results.append((step, result))
        if stop_on_failure and result.status != "success":
            break
    return results
