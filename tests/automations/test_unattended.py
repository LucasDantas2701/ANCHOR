"""Unattended runs: only a proven plan, nothing repaired or asked, and a stop at any change."""

import pytest

from anchor.automations import Automation, AutomationError, AutomationStore, run_automation
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.memory import ChoiceMemory
from anchor.planner import Goal, Plan, Step

FORM = """<html><body>
  <label for="nome">Nome</label><input id="nome">
  <button onclick="document.getElementById('m').textContent='Cadastro salvo'; document.body.dataset.saved = this.textContent">{save}</button>
  {extra}
  <p id="m" role="status"></p></body></html>"""
GOALS = [Goal("g1", "nome preenchido"), Goal("g2", "cadastro salvo", True)]
PLAN = [("fill", "Nome", "Maria", "g1", None), ("click", "Salvar", None, "g2", "salvo")]


class Learner:
    def __init__(self, *plans):
        self.plans = list(plans)

    def plan(self, *args, **kwargs):
        goals, steps = self.plans.pop(0) if self.plans else ([], [])
        return Plan(steps=[Step(*s) for s in steps], goals=goals)


def no_model(_automation):
    raise AssertionError("an unattended run must never call the model")


@pytest.fixture
def store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="register", request="cadastre a Maria e salve", url="about:blank", profile="x"))
    return s


def run(store, page, make_planner, html, **kw):
    page.set_content(html)
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("register")))
    return run_automation(store, "register", page, executor, make_planner, report=None, **kw)


def learned(store, page):
    """The first run, with someone present: it learns the plan and proves it."""
    result, mode, _ = run(store, page, lambda _: Learner((GOALS, PLAN), ([], [])), FORM.format(save="Salvar", extra=""))
    assert result.ok and mode == "learn"


def test_a_plan_learned_with_someone_present_is_proven_and_runs_unattended(page, store):
    learned(store, page)
    plan = store.load_plan("register")
    assert plan.proven_run and plan.proven_elements["click|Salvar"] == "Salvar"
    result, mode, _ = run(store, page, no_model, FORM.format(save="Salvar", extra=""), unattended=True)
    assert result.ok and mode == "replay" and page.evaluate("document.body.dataset.saved") == "Salvar"
    assert store.runs("register")[-1]["unattended"] is True


def test_an_automation_never_proven_does_not_run_unattended(page, store):
    with pytest.raises(AutomationError, match="cannot run unattended"):
        run(store, page, no_model, FORM.format(save="Salvar", extra=""), unattended=True)


def test_a_step_that_would_act_on_another_element_stops_before_acting(page, store):
    """The button now says "Salvar rascunho": with someone present it could be right; unattended, it is a change."""
    learned(store, page)
    result, _, _ = run(store, page, no_model, FORM.format(save="Salvar rascunho", extra=""), unattended=True)
    assert not result.ok and "proving run" in result.message
    assert page.evaluate("document.body.dataset.saved") is None          # nothing clicked


def test_nothing_is_repaired_unattended(page, store):
    """The button is gone: with someone present the model would repair; unattended, the run stops."""
    learned(store, page)
    result, _, _ = run(store, page, no_model, FORM.format(save="Enviar", extra=""), unattended=True)
    assert not result.ok and result.llm_calls == 0
    assert store.load_plan("register").steps[1].description == "Salvar"     # the plan is untouched


def test_a_plan_changed_by_a_repair_is_no_longer_proven(page, store):
    """A repair, relearning or an undo saves a new plan, and a new plan is born with no proof."""
    from anchor.automations.model import ApprovedPlan
    learned(store, page)
    plan = store.load_plan("register")
    store.save_plan("register", ApprovedPlan(steps=plan.steps, goals=plan.goals, source_run="repair"))
    assert not store.load_plan("register").proven_run
    with pytest.raises(AutomationError, match="cannot run unattended"):
        run(store, page, no_model, FORM.format(save="Salvar", extra=""), unattended=True)
    # One clean run with someone present proves the new plan again.
    result, _, _ = run(store, page, no_model, FORM.format(save="Salvar", extra=""))
    assert result.ok and store.load_plan("register").proven_run


def test_a_cookie_banner_is_still_declined_unattended(page, store):
    """Declining a banner does not change the plan: the steps still act on the proven elements."""
    learned(store, page)
    banner = ('<div role="dialog" aria-modal="true" style="position:fixed;inset:0;background:#fff;z-index:9">'
              '<p>Usamos cookies.</p><button onclick="this.parentElement.remove()">Recusar</button></div>')
    result, _, _ = run(store, page, no_model, FORM.format(save="Salvar", extra=banner), unattended=True)
    assert result.ok and page.evaluate("document.body.dataset.saved") == "Salvar"
