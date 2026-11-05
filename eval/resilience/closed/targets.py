"""
Records, once, which element each step of a base task's reference plan acts on, as the evaluation's
marker (data-eval), on the ORIGINAL (L0) pages, which are development pages the engine already knows.

    python -m eval.resilience.closed.targets

The reference plan runs there through the agent, as in development, and after each step the marker of
the element the resolver chose is read and checked against the task's allowed elements. The closed
set's check then uses only these markers, with plain Playwright and no part of ANCHOR: ANCHOR never
runs on a closed page before the final run. Writes eval/resilience/closed/reference_targets.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "plans" / "resilience_tasks.json"
OUT = Path(__file__).resolve().parent / "reference_targets.json"


def base_tasks() -> list[dict]:
    return [t for t in json.loads(TASKS.read_text(encoding="utf-8"))["tasks"] if t["level"] == 0]


def allowed_tokens(task: dict) -> set[str]:
    return {m.group(1) for a in task["allowed"] for m in re.finditer(r"data-eval~=(\w+)", a)}


def record() -> dict:
    from anchor.engine.action_executor import ActionExecutor
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner.execute import run_step
    from eval.plan_run import FIXTURES, INSTRUMENT, ReferencePlanner

    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for t in base_tasks():
            page = browser.new_page()
            page.add_init_script(INSTRUMENT)
            page.set_default_timeout(5000)
            page.goto((FIXTURES / t["fixture"]).as_uri())
            planner = ReferencePlanner()
            planner.current = t["reference"]
            plan = planner.plan(t["request"], page.url, None)
            executor = ActionExecutor(page, resolver=ElementResolver(page))
            steps = []
            for step in plan.steps:
                result = run_step(executor, step)
                token = ""
                if result.selected_element is not None:
                    try:
                        token = (result.selected_element.locator.get_attribute("data-eval", timeout=1000) or "").split()
                    except Exception:
                        token = []
                    token = " ".join(token)
                steps.append({"action": step.action, "description": step.description, "value": step.value,
                              "eval": token, "status": result.status})
            ok = all(s["status"] == "success" for s in steps)
            tokens = allowed_tokens(t)
            acting = [s for s in steps if s["action"] not in ("extract", "wait", "goto", "scroll")]
            inside = all(s["eval"] and set(s["eval"].split()) & tokens for s in acting)
            checks = all(bool(page.evaluate(f"() => Boolean({c})")) for c in t["checks"])
            out[t["base_task"]] = {"fixture": t["fixture"], "steps": steps, "done": ok and checks, "markers_allowed": inside}
            page.close()
        browser.close()
    return out


def main() -> int:
    targets = record()
    OUT.write_text(json.dumps({"_readme": "Written by python -m eval.resilience.closed.targets on the L0 (development) "
                                          "pages: the marker of the element each reference step acts on.",
                               "tasks": targets}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bad = [k for k, v in targets.items() if not (v["done"] and v["markers_allowed"])]
    print(f"{len(targets)} base tasks; {len(targets) - len(bad)} with every step on an allowed marker and the checks met.")
    for k in bad:
        print("  NOT OK:", k)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
