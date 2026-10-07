"""The resilience benchmark's ANCHOR executor and report (with a fake model)."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright  # noqa: F401

from anchor.planner import Plan, Step
from eval.resilience.report import print_tables
from eval.resilience.run import TASKS, run_anchor

ALL = {t["id"]: t for t in json.loads(Path(TASKS).read_text(encoding="utf-8"))["tasks"]}


def no_model(_automation):
    raise AssertionError("this level should not need the model")


class Healer:
    """A fake model for healing: one batch of steps per call, then "nothing is left"."""

    def __init__(self, *batches):
        self.batches, self.calls = list(batches), 0

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.calls += 1
        steps = self.batches.pop(0) if self.batches else []
        return Plan(steps=[Step(*s) for s in steps])


def test_a_level_the_saved_plan_survives_needs_no_model(browser, tmp_path):
    rows = run_anchor(browser, ALL["p-log-02@L3"], no_model, "fake", tmp_path)
    assert [r.success for r in rows] == [True, True] and all(r.llm_calls == 0 for r in rows)


def test_a_broken_plan_is_healed_and_then_reused_without_the_model(browser, tmp_path):
    task = ALL["p-log-02@L4"]                       # a cookie banner covers the page; the list is hidden
    healer = Healer([("click", "Aceitar cookies", None)], [("click", "Mostrar mais", None)],
                    [("select", "Language", "Português")])
    rows = run_anchor(browser, task, lambda _a: healer, "fake", tmp_path)
    first, second = rows
    assert first.success and first.healed and first.llm_calls >= 1
    assert second.success and second.llm_calls == 0          # reused: the corrected plan, no model


def test_the_report_counts_reuse_only_without_the_model():
    base = dict(executor="anchor", profile="m", level=4, language="pt", false_success=False, unrequested=0,
                attacked=False, attack_attempts=0, seconds=1.0, healed=False)
    rows = [dict(base, run=1, success=True, llm_calls=2), dict(base, run=2, success=True, llm_calls=1)]
    summary = print_tables(rows)
    assert summary["anchor recovery (m) [pt]"]["success"] == 1.0
    assert summary["anchor reuse (m) [pt]"]["success"] == 0.0      # it needed the model again


def test_a_recovery_that_does_not_redo_the_saved_step_is_not_a_success(browser, tmp_path):
    """The model closes the banner and says nothing is left: the language was never chosen."""
    task = ALL["p-log-02@L4"]
    rows = run_anchor(browser, task, lambda _a: Healer([("click", "Aceitar cookies", None)]), "fake", tmp_path)
    assert not rows[0].success and not rows[0].claimed_success and not rows[0].false_success
