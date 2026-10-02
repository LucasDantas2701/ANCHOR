"""Saved automations: the first run learns the plan, the next ones replay it without the LLM."""

import pytest

from anchor.automations import Automation, AutomationError, AutomationStore, run_automation
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.memory import ChoiceMemory
from anchor.planner import Goal, Plan, Step

FORM = """<html><body>
  <label for="nome">Nome</label><input id="nome">
  <button onclick="document.getElementById('m').textContent='Cadastro salvo'">{save}</button>
  <p id="m" role="status"></p></body></html>"""


class LearningPlanner:
    """Plays the LLM in the learning run: a ready-made plan, then "nothing is left"."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), 0

    def plan(self, request, url, page_elements=None, history=None, **_):
        self.calls += 1
        goals, steps = self.plans.pop(0) if self.plans else ([], [])
        return Plan(steps=[Step(*s) for s in steps], goals=goals)


def no_llm(_automation):
    raise AssertionError("a replay must not call the LLM")


GOALS = [Goal("g1", "nome preenchido"), Goal("g2", "cadastro salvo", True)]
PLAN = [("fill", "Nome", "Maria", "g1", None), ("click", "Salvar", None, "g2", "salvo")]


@pytest.fixture
def store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="register", request="cadastre a Maria e salve", url="about:blank", profile="x"))
    return s


def run(store, page, make_planner, **kw):
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("register")))
    return run_automation(store, "register", page, executor, make_planner, report=None, **kw)


def test_first_run_learns_and_saves_the_plan_that_worked(page, store):
    page.set_content(FORM.format(save="Salvar"))
    planner = LearningPlanner((GOALS, [("click", "Botão que não existe", None, "g1", None)]),
                              ([], PLAN), ([], []))
    result, mode, run_id = run(store, page, lambda _: planner)
    assert result.ok and mode == "learn"
    plan = store.load_plan("register")
    assert [(s.action, s.description) for s in plan.steps] == [("fill", "Nome"), ("click", "Salvar")]
    assert {g.id for g in plan.goals} == {"g1", "g2"} and plan.source_run == run_id
    assert store.runs("register")[0]["mode"] == "learn"


def test_next_runs_replay_without_the_llm(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Salvar"))
    result, mode, _ = run(store, page, no_llm)
    assert result.ok and mode == "replay" and result.llm_calls == 0
    assert page.input_value("#nome") == "Maria" and "Cadastro salvo" in page.inner_text("body")


def test_replay_stops_when_the_site_changed(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.replace('<button onclick="document.getElementById(\'m\').textContent=\'Cadastro salvo\'">{save}</button>', ""))
    result, mode, _ = run(store, page, no_llm)              # the save button is gone
    assert mode == "replay" and result.status == "failed"
    assert result.message.startswith("the saved plan stopped working")
    assert store.runs("register")[-1]["status"] == "failed"


def test_failed_learning_saves_no_plan(page, store):
    page.set_content(FORM.format(save="Salvar"))
    bad = [("click", "Botão que não existe", None, "g1", None)]
    run(store, page, lambda _: LearningPlanner((GOALS, bad), ([], bad), ([], bad)))
    assert store.load_plan("register") is None


def test_relearn_replaces_the_approved_plan(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Gravar dados"))
    new_plan = [("fill", "Nome", "Maria", "g1", None), ("click", "Gravar dados", None, "g2", None)]
    result, mode, _ = run(store, page, lambda _: LearningPlanner((GOALS, new_plan), ([], [])), relearn=True)
    assert result.ok and mode == "learn"
    assert store.load_plan("register").steps[1].description == "Gravar dados"


def test_replay_follows_a_page_change(page, store, tmp_path):
    (tmp_path / "p2.html").write_text('<html><body><label for="c">CPF</label><input id="c">'
                                      '<button onclick="document.body.dataset.ok=1">Enviar</button></body></html>',
                                      encoding="utf-8")
    (tmp_path / "p1.html").write_text('<html><body><label for="n">Nome</label><input id="n">'
                                      '<a href="p2.html">Próximo</a></body></html>', encoding="utf-8")
    steps = [("fill", "Nome", "Maria", "g1", None), ("click", "Próximo", None, "g1", None),
             ("fill", "CPF", "123", "g2", None), ("click", "Enviar", None, "g2", None)]
    goals = [Goal("g1", "nome"), Goal("g2", "enviado", True)]
    store.create(Automation(name="wizard", request="preencha a Maria, o CPF 123 e envie", url="x", profile="x"))

    def run_wizard(make_planner):
        page.set_default_timeout(1500)
        executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("wizard")))
        return run_automation(store, "wizard", page, executor, make_planner, report=None)

    page.goto((tmp_path / "p1.html").as_uri())
    learned, _, _ = run_wizard(lambda _: LearningPlanner((goals, steps[:2]), ([], steps[2:]), ([], [])))
    assert learned.ok and len(store.load_plan("wizard").steps) == 4
    page.goto((tmp_path / "p1.html").as_uri())
    result, mode, _ = run_wizard(no_llm)
    assert result.ok and mode == "replay" and page.input_value("#c") == "123"


def test_names_and_missing_automations(tmp_path):
    store = AutomationStore(tmp_path)
    with pytest.raises(AutomationError, match="invalid name"):
        store.create(Automation(name="Com Espaço", request="x", url="x", profile="x"))
    with pytest.raises(AutomationError, match="does not exist"):
        store.load("nope")
    assert store.names() == []



def test_replay_survives_a_renamed_button_with_the_same_meaning(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Gravar dados"))      # "gravar" means "salvar"
    result, mode, _ = run(store, page, no_llm)
    assert result.ok and mode == "replay"
