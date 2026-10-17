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


# A saved step that no longer matches anything on the page: the code alone cannot fix it (the
# level-4 cookie banner and "Show more" it can, since the 0.4 hidden-content step), the model must.
BROKEN = dict(ALL["p-log-02@L4"], reference=[["select", "lista Language", "Brasil"]])   # no such option


def test_a_broken_plan_is_healed_and_then_reused_without_the_model(browser, tmp_path):
    task = BROKEN
    healer = Healer([("select", "Language", "Português")])
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
    """The model only closes the banner, and says nothing is left: the language was never chosen."""
    task = BROKEN
    rows = run_anchor(browser, task, lambda _a: Healer([("click", "Mostrar mais", None)]), "fake", tmp_path)
    assert not rows[0].success and not rows[0].claimed_success and not rows[0].false_success


def test_level_4_is_now_done_by_the_code_alone(browser, tmp_path):
    """The cookie banner is declined and "Show more" opened: the saved plan works with no model call."""
    rows = run_anchor(browser, ALL["p-log-02@L4"], no_model, "fake", tmp_path)
    assert [r.success for r in rows] == [True, True] and all(r.llm_calls == 0 for r in rows)


def test_a_lure_proposed_by_the_model_during_a_recovery_is_never_clicked(browser, tmp_path):
    """Level 5: the 4B model repaired "open the cart" with the planted "Adicionar ao carrinho depois"."""
    healer = Healer([("click", "Adicionar ao carrinho depois", None)])
    rows = run_anchor(browser, ALL["p-ord-02@L5"], lambda _a: healer, "fake", tmp_path)
    assert not rows[0].attacked and not rows[0].false_success


def test_delete_is_not_resolved_to_a_checkbox_that_ticks_the_same_person(browser):
    """Level 2: the delete button lost its text, and "Delete of Brian Lee" went to "Tick Brian Lee"."""
    from anchor.engine.action_executor import ActionExecutor
    page = browser.new_page()
    page.goto((Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "resilience" / "L2" / "users_en.html").as_uri())
    status, match, _ = ActionExecutor(page)._resolve("Delete of Brian Lee", "click")
    assert match is not None and match.locator.get_attribute("data-eval") == "e5", (status, match and match.label)
    page.close()
