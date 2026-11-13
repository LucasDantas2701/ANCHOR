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
import re
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
    extractions: list = field(default_factory=list)    # what was read, in the agent's format (see plan_run)


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


def _act(target, action: str, value, timeout_ms: int) -> None:
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


def run_script(page: Page, script: list[list], timeout_ms: int = 3000) -> Outcome:
    """Replays a recorded script blindly, as a traditional RPA robot would."""
    start, steps = time.perf_counter(), []
    for action, selector, value in script:
        target = page.locator(selector).first
        try:
            if target.count() == 0:
                raise LookupError("the selector finds nothing")
            _act(target, action, value, timeout_ms)
            steps.append([action, selector, value, "success"])
        except Exception as exc:
            steps.append([action, selector, value, "failed"])
            return Outcome("script", False, steps, str(exc).splitlines()[0][:200], seconds=round(time.perf_counter() - start, 2))
    return Outcome("script", True, steps, seconds=round(time.perf_counter() - start, 2))


# --------------------------------------------------------------------------
# Script with role and text locators (decided on 13/11/2026): the robust way of writing a script by hand
# with Playwright, recorded on L0 from the same reference plan as the fixed-selector one
# --------------------------------------------------------------------------

_SNAPSHOT = re.compile(r'^- ([a-z]+)(?: "((?:[^"\\]|\\.)*)")?')
_NO_ROLE = {"generic", "text", "paragraph", "group", "none", "presentation", "img"}


def role_locator(page: Page, spec: dict):
    """The Playwright locator a role-and-text script uses: getByRole(role, name) or getByText(text), exact."""
    if "role" in spec and "name" in spec:
        found = page.get_by_role(spec["role"], name=spec["name"], exact=True)
    elif "role" in spec:
        found = page.get_by_role(spec["role"])                # no name to use: the role and its position
    else:
        found = page.get_by_text(spec["text"], exact=True)
    return found.nth(spec.get("nth", 0))


def describe_by_role(page: Page, element_id: str) -> dict | None:
    """The element's role and accessible name, as Playwright computes them (its ARIA snapshot), or its text
    when it has no meaningful role, or, with neither (an icon), its role alone; with its position among the
    elements the locator finds (0 when unique)."""
    handle = page.locator(f'[data-er-id="{element_id}"]').first
    if not handle.count():
        return None
    match = _SNAPSHOT.match(handle.aria_snapshot().splitlines()[0].strip())
    role, name = (match.group(1), (match.group(2) or "").replace('\\"', '"')) if match else (None, "")
    text = " ".join(handle.inner_text().split())
    if role and name and role not in _NO_ROLE:
        spec = {"role": role, "name": name}
        found = page.get_by_role(role, name=name, exact=True)
    elif text:
        spec = {"text": text}
        found = page.get_by_text(text, exact=True)
    elif role and role not in _NO_ROLE:
        spec = {"role": role}                                 # no name and no text (an icon): the role's position
        found = page.get_by_role(role)
    else:
        return None
    for i in range(found.count()):
        if found.nth(i).get_attribute("data-er-id") == element_id:
            if i:
                spec["nth"] = i
            return spec
    return None


class _RoleRecorder(ActionExecutor):
    """Notes the role-and-text locator of every element right before acting on it (on the L0 page)."""

    def __init__(self, page: Page, **kwargs):
        super().__init__(page, **kwargs)
        self.spec = None

    def _denied(self, action_name, description, match, resolved_by="memory"):
        self.spec = describe_by_role(self.page, match.id)
        return super()._denied(action_name, description, match, resolved_by)


def record_role_script(page: Page, reference: list) -> list[list]:
    """The reference plan, run on the page as it is now (L0), as [action, locator, value] steps."""
    recorder = _RoleRecorder(page, resolver=ElementResolver(page))
    script = []
    for action, description, value in reference:
        recorder.spec = None
        result = run_step(recorder, Step(action, description, value))
        if result.status != "success" or not recorder.spec:
            raise RuntimeError(f"could not record {action} {description!r} by role or text: {result.status}")
        script.append([action, recorder.spec, value])
    return script


def run_role_script(page: Page, script: list[list], timeout_ms: int = 3000) -> Outcome:
    """Replays a role-and-text script: each step finds its element again by role and name (or text)."""
    start, steps = time.perf_counter(), []
    for action, spec, value in script:
        shown = json.dumps(spec, ensure_ascii=False)
        try:
            target = role_locator(page, spec)
            if target.count() == 0:
                raise LookupError("the locator finds nothing")
            _act(target, action, value, timeout_ms)
            steps.append([action, shown, value, "success"])
        except Exception as exc:
            steps.append([action, shown, value, "failed"])
            return Outcome("roles", False, steps, str(exc).splitlines()[0][:200], seconds=round(time.perf_counter() - start, 2))
    return Outcome("roles", True, steps, seconds=round(time.perf_counter() - start, 2))


# --------------------------------------------------------------------------
# LLM in control
# --------------------------------------------------------------------------

LLM_SYSTEM = """Você controla um navegador para cumprir o pedido do usuário. A cada vez, você recebe \
o pedido, a lista numerada dos elementos da página e o que já fez. Responda só com um JSON com a \
próxima ação, sem texto antes ou depois:
{"action": "click" | "fill" | "select" | "check" | "uncheck" | "press" | "read" | "read_table" | "done", "element": número, "value": texto ou null}
fill: value é o texto a digitar; select: value é o texto da opção; press: value é a tecla (ex.: "Enter").
read: lê um texto da página, e value descreve o que ler (ex.: "o total do pedido"); read_table: lê \
inteira a tabela ou lista cujo nome está em value. Nas duas, element pode ser null. Use-as quando o pedido \
pede uma informação da página.
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


LLM_SEED = 7       # the same seed as ANCHOR's planner (decided on 13/11/2026, with the determinism check)


def plan_lines(plan: list) -> list[str]:
    """A reference plan as guidance for the model: one line per step (action, element, value)."""
    return [f"{i}. {action} \"{element}\"" + (f" = \"{value}\"" if value not in (None, "") else "")
            for i, (action, element, value) in enumerate(plan, 1)]


def run_llm(page: Page, request: str, client, model: str, max_steps: int = 12, timeout_ms: int = 3000,
            plan: list | None = None) -> Outcome:
    """The LLM chooses every action and element; the action is performed directly on it. With a plan (the
    task's reference plan, the one ANCHOR's saved automation and the scripts come from), the model gets it as
    guidance, so all the systems start from the same point (decided on 13/11/2026); without one, it plans
    from scratch."""
    start, steps, done = time.perf_counter(), [], []
    outcome = Outcome("llm", False)
    resolver = ElementResolver(page)
    for _ in range(max_steps):
        lines, ids = numbered_elements(resolver)
        history = "\n".join(f"- {d}" for d in done) or "- (nada ainda)"
        guide = ("Plano de referência (os passos que fazem o pedido; use como orientação):\n"
                 + "\n".join(plan_lines(plan)) + "\n\n") if plan else ""
        user = f"Pedido: {request}\n\n{guide}Já feito:\n{history}\n\nElementos:\n" + "\n".join(lines)
        response = client.chat.completions.create(
            model=model, temperature=0, seed=LLM_SEED,
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
        if action in ("read", "read_table"):
            # ANCHOR's own readings (the same engine code as its extract_text and extract_table), by what
            # the model describes: the element list holds only interactive elements, and so does ANCHOR's
            # reading not depend on one (decided on 13/11/2026)
            reader = ActionExecutor(page, resolver=ElementResolver(page))
            read = (reader.extract_text if action == "read" else reader.extract_table)(str(value or ""))
            if read.status == "success" and read.value is not None:
                if action == "read":
                    text = " ".join(str(read.value).split())
                    outcome.extractions.append({"kind": "text", "description": str(value), "text": text})
                    done.append(f'read "{value}": "{text[:150]}"')
                else:
                    table = read.value
                    outcome.extractions.append({"kind": table.kind, "description": str(value), "name": table.label(),
                                                "rows": len(table.rows), "columns": table.columns})
                    done.append(f'read_table "{value}": {table.label()}, {len(table.rows)} linhas')
                steps.append([action, str(value), None, "success"])
            else:
                steps.append([action, str(value), None, "failed"])
                done.append(f'falhou: {action} "{value}" ({read.status})')
            continue
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
