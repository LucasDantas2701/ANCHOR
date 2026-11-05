"""
The closed set's reference executor: plain Playwright, no part of ANCHOR. It does a base task's
reference plan on a page by the evaluation's markers recorded on L0 (reference_targets.json), and says
whether the task's checks are met. It only answers whether a perturbed task is still possible; it is
never one of the measured executors (which may not use the markers).
"""
from __future__ import annotations

import json
from pathlib import Path

TARGETS = Path(__file__).resolve().parent / "reference_targets.json"


def load_targets() -> dict:
    return json.loads(TARGETS.read_text(encoding="utf-8"))["tasks"]


def do(page, steps: list[dict], timeout: int = 3000) -> str:
    """Does the steps; "" when every one was done, or what stopped it."""
    page.on("dialog", lambda d: d.accept())                # a person could answer a pop-up box; ANCHOR's rule is apart
    for i, s in enumerate(steps, 1):
        el = page.locator(f'[data-eval~="{s["eval"].split()[0]}"]').first
        try:
            if s["action"] == "click":
                el.click(timeout=timeout)
            elif s["action"] == "fill":
                el.fill(s["value"] or "", timeout=timeout)
            elif s["action"] == "check":
                el.check(timeout=timeout)
            elif s["action"] == "select":
                try:
                    el.select_option(label=s["value"], timeout=timeout)
                except Exception:
                    el.select_option(s["value"], timeout=timeout)
            elif s["action"] == "press":
                el.press(s["value"] or "Enter", timeout=timeout)
            else:
                return f"step {i}: action {s['action']!r} not known"
        except Exception as exc:
            return f"step {i} ({s['action']}): {type(exc).__name__}"
        page.wait_for_timeout(50)
    return ""


def possible(page, url: str, task: dict, steps: list[dict]) -> tuple[bool, str]:
    """Whether the task can still be done on the page at url: the steps run and its checks are met."""
    page.goto(url)
    stopped = do(page, steps)
    if stopped:
        return False, stopped
    failed = [i for i, c in enumerate(task["checks"], 1) if not page.evaluate(f"() => Boolean({c})")]
    return not failed, f"checks failing: {failed}" if failed else ""
