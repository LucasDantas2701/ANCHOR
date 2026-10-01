"""Runs a plan with the ActionExecutor, step by step."""

from __future__ import annotations

import re

from anchor.engine.action_executor import ActionExecutor, ActionResult
from anchor.engine.disambiguation.describe import kinds
from anchor.i18n import SUPPORTED

from .plan import Plan, Step

# Multi-word kind labels used by the page summary ("Campo de texto", "Text field",
# "Caixa de marcação"...), in both languages. Models tend to copy them into the
# description, and words like "texto" match every field on the page. One-word
# labels ("Botão", "Link") stay: they help the heuristic.
_MULTIWORD_KINDS = sorted({k for lang in SUPPORTED for k in kinds(lang).values() if " " in k},
                          key=len, reverse=True)
_KIND_RE = re.compile(r"^(?:" + "|".join(re.escape(k) for k in _MULTIWORD_KINDS) + r")\s+", re.IGNORECASE)
_QUOTES_RE = re.compile(r"[\"“”]")
_POPUP_RE = re.compile(r"\s*\[pop-up\]", re.IGNORECASE)


def clean_description(text: str) -> str:
    """Removes kind labels and the [pop-up] mark copied from the page summary, and quotes."""
    cleaned = _QUOTES_RE.sub("", _KIND_RE.sub("", _POPUP_RE.sub("", text).strip())).strip()
    return cleaned or text


def clean_value(value):
    """Removes brackets, quotes and the "opções:"/"options:" label copied from the page summary."""
    if value is None:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^\[?\s*(opç(ões|oes)|options):\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip("[]\"“” ").strip()
    return cleaned or value


def run_step(executor: ActionExecutor, step: Step) -> ActionResult:
    a, d, v = step.action, clean_description(step.description), clean_value(step.value)
    if a == "fill":
        return executor.fill(d, v)
    if a == "select":
        result = executor.select(d, label=v)
        # A "select" that did not work may be a radio button or a checkbox
        # described as an "option": try checking it, and use it only if it works.
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
