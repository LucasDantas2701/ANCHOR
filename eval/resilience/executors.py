"""
The two executors ANCHOR is compared with, in the resilience benchmark.

Traditional script (fixed selectors). The reference plan is "recorded" on the original page
(L0): each step is resolved there, and the element becomes a fixed selector, as classic RPA
recorders do (Selenium, BotCity): its id; else its name or test attribute; else the path of
classes and positions up to an ancestor with an id. On an altered page, the script replays the
selectors and values blindly: a selector that finds nothing, or a blocked action, fails the step.
When every step runs without an error, the script claims success; the task's checks say whether
it really was one.

LLM in control (in the style of Steward). At every step, the model gets the request, the
numbered list of the page's elements (described as ANCHOR describes them to its planner, with the
same filters: elements covered by a pop-up are left out, those in a pop-up are marked) and what it
has done so far, and answers with an action and a number. The action is performed directly on that
element: no heuristic, no barriers, no confirmation, no effect check, no memory. Same model as ANCHOR.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Page

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation.describe import describe
from anchor.engine.element_resolver import ElementResolver
from anchor.planner import Step
from anchor.planner.execute import run_step


@dataclass
class Outcome:
    executor: str
    claimed_success: bool
    steps: list = field(default_factory=list)       # [action, target, value, status]
    error: str = ""
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


# --------------------------------------------------------------------------
# Traditional script
# --------------------------------------------------------------------------

RECORD_JS = r"""(e) => {
    const q = (s) => CSS.escape(s);
    if (e.id) return "#" + q(e.id);
    for (const a of ["data-test", "data-testid", "name"]) {
        const v = e.getAttribute(a);
        if (!v) continue;
        const selector = e.tagName.toLowerCase() + "[" + a + '="' + v.replace(/"/g, '\\"') + '"]';
        if (document.querySelectorAll(selector).length === 1) return selector;   // only if unique
    }
    const parts = [];
    for (let n = e; n && n.nodeType === 1 && n !== document.body; n = n.parentElement) {
        if (n.id) { parts.unshift("#" + q(n.id)); break; }
        let s = n.tagName.toLowerCase();
        const classes = [...n.classList].slice(0, 2);
        if (classes.length) s += "." + classes.map(q).join(".");
        const same = [...n.parentElement.children].filter((c) => c.tagName === n.tagName);
        if (same.length > 1) s += ":nth-of-type(" + (same.indexOf(n) + 1) + ")";
        parts.unshift(s);
    }
    return parts.join(" > ");
}"""


class _Recorder(ActionExecutor):
    """Notes the fixed selector of every element right before acting on it (on the L0 page)."""

    def __init__(self, page: Page, **kwargs):
        super().__init__(page, **kwargs)
        self.selector = None

    def _denied(self, action_name, description, match, resolved_by="memory"):
        handle = self.page.locator(f'[data-er-id="{match.id}"]').first
        self.selector = handle.evaluate(RECORD_JS) if handle.count() else None
        return super()._denied(action_name, description, match, resolved_by)


def record_script(page: Page, reference: list) -> list[list]:
    """The reference plan, run on the page as it is now (L0), as [action, selector, value] steps."""
    recorder = _Recorder(page, resolver=ElementResolver(page))
    script = []
    for action, description, value in reference:
        recorder.selector = None
        result = run_step(recorder, Step(action, description, value))
        if result.status != "success" or not recorder.selector:
            raise RuntimeError(f"could not record {action} {description!r}: {result.status}")
        script.append([action, recorder.selector, value])
    return script


def run_script(page: Page, script: list[list], timeout_ms: int = 3000) -> Outcome:
    """Replays a recorded script blindly, as a traditional RPA robot would."""
    start, steps = time.perf_counter(), []
    for action, selector, value in script:
        target = page.locator(selector).first
        try:
            if target.count() == 0:
                raise LookupError("the selector finds nothing")
            if action == "click":
                target.click(timeout=timeout_ms)
            elif action == "fill":
                target.fill(value or "", timeout=timeout_ms)
            elif action == "select":
                target.select_option(label=value, timeout=timeout_ms)
            elif action == "check":
                target.check(timeout=timeout_ms)
            elif action == "uncheck":
                target.uncheck(timeout=timeout_ms)
            elif action == "press":
                target.press(value or "Enter", timeout=timeout_ms)
            steps.append([action, selector, value, "success"])
        except Exception as exc:
            steps.append([action, selector, value, "failed"])
            return Outcome("script", False, steps, str(exc).splitlines()[0][:200], seconds=round(time.perf_counter() - start, 2))
    return Outcome("script", True, steps, seconds=round(time.perf_counter() - start, 2))


# --------------------------------------------------------------------------
# LLM in control
# --------------------------------------------------------------------------

LLM_SYSTEM = """Você controla um navegador para cumprir o pedido do usuário. A cada vez, você recebe \
o pedido, a lista numerada dos elementos da página e o que já fez. Responda só com um JSON com a \
próxima ação, sem texto antes ou depois:
{"action": "click" | "fill" | "select" | "check" | "uncheck" | "press" | "done", "element": número, "value": texto ou null}
fill: value é o texto a digitar; select: value é o texto da opção; press: value é a tecla (ex.: "Enter").
Use "done" quando o pedido estiver cumprido. Elementos marcados com [pop-up] estão num diálogo ou \
menu aberto por cima da página."""


def numbered_elements(resolver: ElementResolver, limit: int = 80) -> tuple[list[str], list[str]]:
    """(the lines shown to the model, the element ids in the same order)."""
    resolver.index("interactive")
    records = [r for r in resolver.records if not r.get("obscured")]
    records.sort(key=lambda r: 0 if r.get("layer") else 1)
    records = records[:limit]
    views = [describe(resolver.to_match(r), 0, language="pt") for r in records]
    # As in ANCHOR's page summary: the context only for elements whose names repeat.
    repeated = {}
    for v in views:
        repeated[(v.kind, v.name)] = repeated.get((v.kind, v.name), 0) + 1
    lines, ids = [], []
    for record, v in zip(records, views):
        line = f'[{len(ids) + 1}] {v.kind} "{v.name}"'
        if repeated[(v.kind, v.name)] > 1 and v.near:
            line += f" ({v.near[:40]})"
        if record.get("options"):
            line += " [opções: " + " | ".join(record["options"][:10]) + "]"
        if record.get("layer"):
            line += " [pop-up]"
        lines.append(line)
        ids.append(record["id"])
    return lines, ids


def _parse(text: str) -> Optional[dict]:
    from anchor.planner.planner import _extract_json
    try:
        data = _extract_json(text)
    except Exception:
        return None
    return data if isinstance(data, dict) and data.get("action") else None


def run_llm(page: Page, request: str, client, model: str, max_steps: int = 12, timeout_ms: int = 3000) -> Outcome:
    """The LLM chooses every action and element; the action is performed directly on it."""
    start, steps, done = time.perf_counter(), [], []
    outcome = Outcome("llm", False)
    resolver = ElementResolver(page)
    for _ in range(max_steps):
        lines, ids = numbered_elements(resolver)
        history = "\n".join(f"- {d}" for d in done) or "- (nada ainda)"
        user = f"Pedido: {request}\n\nJá feito:\n{history}\n\nElementos:\n" + "\n".join(lines)
        response = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}])
        outcome.llm_calls += 1
        usage = getattr(response, "usage", None)
        outcome.tokens_in += getattr(usage, "prompt_tokens", 0) or 0
        outcome.tokens_out += getattr(usage, "completion_tokens", 0) or 0
        answer = _parse(response.choices[0].message.content or "")
        if answer is None:
            outcome.error = "the model's answer is not a valid action"
            break
        action, value = answer["action"], answer.get("value")
        if action == "done":
            outcome.claimed_success = True
            break
        try:
            number = int(answer.get("element"))
            target = page.locator(f'[data-er-id="{ids[number - 1]}"]').first
        except (TypeError, ValueError, IndexError):
            outcome.error = f"no element number {answer.get('element')!r}"
            break
        name = lines[number - 1]
        try:
            if action == "click":
                target.click(timeout=timeout_ms)
            elif action == "fill":
                target.fill(str(value or ""), timeout=timeout_ms)
            elif action == "select":
                target.select_option(label=str(value), timeout=timeout_ms)
            elif action == "check":
                target.check(timeout=timeout_ms)
            elif action == "uncheck":
                target.uncheck(timeout=timeout_ms)
            elif action == "press":
                target.press(str(value or "Enter"), timeout=timeout_ms)
            else:
                raise ValueError(f"unknown action {action!r}")
            steps.append([action, name, value, "success"])
            done.append(f"{action} {name}" + (f' = "{value}"' if value is not None else ""))
        except Exception as exc:
            steps.append([action, name, value, "failed"])
            done.append(f"falhou: {action} {name} ({str(exc).splitlines()[0][:80]})")
        page.wait_for_timeout(200)
    else:
        outcome.error = f"limit of {max_steps} steps reached"
    outcome.steps = steps
    outcome.seconds = round(time.perf_counter() - start, 2)
    return outcome
