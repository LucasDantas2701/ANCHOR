"""
Goals (checkpoints) and expected effects: the end is only declared with all
goals fulfilled, and an expected text that does not appear becomes a suspicion.
"""

import json

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Goal, LLMPlanner, Plan, PlanError, Step, check_request
from tests.planner.test_planner import FakeClient

FORM = """<html><body>
  <label for="nome">Nome</label><input id="nome">
  <label for="mail">E-mail</label><input id="mail">
  <button onclick="document.getElementById('m').textContent='Cadastro salvo'">Salvar</button>
  <p id="m" role="status"></p>
</body></html>"""

G = [Goal("g1", "nome preenchido"), Goal("g2", "e-mail preenchido"), Goal("g3", "cadastro salvo", True)]


class GoalPlanner:
    """Returns ready-made plans (with goals) and keeps the history it received."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), []

    def plan(self, request, url, page_elements=None, history=None, known_goals=None):
        self.calls.append({"history": list(history or []), "known": set(known_goals or [])})
        goals, steps = self.plans.pop(0) if self.plans else ([], [])
        return Plan(steps=[Step(*s) for s in steps], goals=goals)


def run(page, planner, request="faça a tarefa da página"):
    page.set_default_timeout(1500)
    return Agent(page, planner, ActionExecutor(page), report=None).run(request)


FULL = [("fill", "Nome", "Maria", "g1", None), ("fill", "E-mail", "m@x.com", "g2", None),
        ("click", "Salvar", None, "g3", "Cadastro salvo")]


def test_all_goals_fulfilled(page):
    page.set_content(FORM)
    planner = GoalPlanner((G, FULL), ([], []))
    result = run(page, planner)
    assert result.ok and result.goals_total == 3 and result.goals_done == 3
    assert result.suspicions == 0
    end_check = planner.calls[1]["history"]
    assert any(line.startswith("metas: g1 (nome preenchido): cumprida") for line in end_check)
    assert any("mensagens visíveis na página agora" in line and "Cadastro salvo" in line for line in end_check)


def test_end_with_pending_goal_is_not_success(page):
    page.set_content(FORM)
    planner = GoalPlanner((G, FULL[:2]), ([], []))     # the model "forgets" to save and says it is done
    result = run(page, planner)
    assert result.status == "cancelled"
    assert "pending goals: g3 (cadastro salvo)" in result.message


def test_expected_text_not_appearing_is_a_suspicion_not_a_failure(page):
    page.set_content(FORM.replace("Cadastro salvo", "Pronto"))
    planner = GoalPlanner((G, FULL), ([], []))
    result = run(page, planner)
    assert result.ok and result.suspicions == 1
    assert "expected to see" in result.records[2].note
    assert any(h.startswith("suspeita:") for h in planner.calls[1]["history"])


def test_goal_with_only_a_blocked_destructive_action_is_dropped(page):
    page.set_content("""<html><body>
      <button onclick="document.body.dataset.f=1">Fechar vaga</button>
      <button onclick="document.getElementById('m').textContent='Vaga salva'">Salvar vaga</button>
      <p id="m" role="status"></p></body></html>""")
    goals = [Goal("g1", "vaga fechada"), Goal("g2", "vaga salva", True)]
    steps = [("click", "Fechar vaga", None, "g1", None), ("click", "Salvar vaga", None, "g2", None)]
    result = run(page, GoalPlanner((goals, steps), ([], [])), request="salve a vaga")
    assert result.ok and result.goals_done == 1
    assert result.records[0].status == "blocked"


def test_replanning_uses_the_known_goals(page):
    page.set_content(FORM)
    first = {"goals": [{"id": "g1", "description": "nome", "conclusive": False},
                       {"id": "g2", "description": "salvo", "conclusive": True}],
             "steps": [{"action": "fill", "description": "Campo que não existe", "value": "Maria",
                        "goal": "g1", "expect": None},
                       {"action": "click", "description": "Salvar", "value": None,
                        "goal": "g2", "expect": None}]}
    # The replan refers to "g2" without repeating the list of goals: it must be accepted.
    replan = {"goals": [], "steps": [{"action": "fill", "description": "Nome", "value": "Maria",
                                      "goal": "g1", "expect": None},
                                     {"action": "click", "description": "Salvar", "value": None,
                                      "goal": "g2", "expect": None}]}
    end = {"goals": [], "steps": []}
    client = FakeClient(json.dumps(first), json.dumps(replan), json.dumps(end))
    result = run(page, LLMPlanner(client, "falso"), request="cadastre a Maria")
    assert result.ok and result.goals_done == 2


def test_unknown_goal_in_a_step_is_rejected():
    from anchor.planner import check_goals
    with pytest.raises(PlanError, match='a meta "g9" não existe'):
        check_goals([Step("click", "Salvar", None, "g9")], [Goal("g1", "x", True)])


def test_conclusive_goal_must_come_last():
    from anchor.planner import check_goals
    steps = [Step("click", "Salvar", None, "g2"), Step("fill", "Nome", "Ana", "g1")]
    with pytest.raises(PlanError, match="devem vir por último"):
        check_goals(steps, [Goal("g1", "nome"), Goal("g2", "salvo", True)])


def test_plan_without_goals_is_still_valid():
    from anchor.planner import check_goals
    check_goals([Step("click", "Salvar")], [])        # does not raise



def test_goal_without_steps_is_rejected():
    from anchor.planner import check_goals
    goals = [Goal("g1", "busca feita", True), Goal("g2", "resultado exibido")]
    with pytest.raises(PlanError, match="g2 não tem nenhum"):
        check_goals([Step("click", "Search", None, "g1")], goals)


def test_plan_without_conclusive_goal_is_rejected():
    from anchor.planner import check_goals
    with pytest.raises(PlanError, match="conclusiva"):
        check_goals([Step("click", "Consultor RPA", None, "g1")], [Goal("g1", "vaga aberta")])


def test_goal_abandoned_by_replanning_is_replaced(page):
    page.set_content("""<html><body>
      <select aria-label="Sort by"><option>Featured</option><option>Price: low to high</option></select>
      <button>Botão parado</button></body></html>""")
    goals = [Goal("g1", "lista aberta"), Goal("g2", "produtos ordenados", True)]
    planner = GoalPlanner(
        (goals, [("click", "Botão parado", None, "g1", None)]),          # no effect: fails
        ([], [("select", "Sort by", "Price: low to high", "g2", None)]),  # another way, without g1
        ([], []),
    )
    result = run(page, planner, request="ordene por preço")
    assert result.ok and result.goals_done == 1


def test_clicking_a_checkbox_checks_its_state(page):
    page.set_content('<html><body><label><input type="checkbox" id="c"> Selecionar Ana</label></body></html>')
    goals = [Goal("g1", "Ana selecionada", True)]
    result = run(page, GoalPlanner((goals, [("click", "Selecionar Ana", None, "g1", None)]), ([], [])))
    assert result.ok and result.no_effect == 0 and page.is_checked("#c")


def test_enter_on_the_wrong_element_goes_to_the_last_field(page):
    page.set_content("""<html><body><div class="lupa" style="cursor:pointer">Search /</div>
      <label for="q">Coins</label><input id="q"
        onkeydown="if(event.key==='Enter'){document.getElementById('r').textContent='Resultados'}">
      <p id="r"></p></body></html>""")
    goals = [Goal("g1", "busca feita", True)]
    steps = [("fill", "Coins", "pi", "g1", None), ("press", "Search /", "Enter", "g1", None)]
    result = run(page, GoalPlanner((goals, steps), ([], [])), request="pesquise pi")
    assert result.ok and result.records[1].resolved_by == "enter_in_field"


# --------------------------------------------------------------------------
# Does the plan cover the request? (checked on the initial plan)
# --------------------------------------------------------------------------

def test_plan_missing_the_request_verb_goes_back_to_the_model():
    from anchor.planner import LLMPlanner
    bad = {"goals": [{"id": "g1", "description": "vaga aberta", "conclusive": True}],
           "steps": [{"action": "click", "description": "Consultor RPA", "value": None, "goal": "g1", "expect": None}]}
    good = {"goals": [{"id": "g1", "description": "vaga salva", "conclusive": True}],
            "steps": [{"action": "click", "description": "Consultor RPA", "value": None, "goal": "g1", "expect": None},
                      {"action": "click", "description": "Salvar vaga", "value": None, "goal": "g1", "expect": None}]}
    client = FakeClient(json.dumps(bad), json.dumps(good))
    plan = LLMPlanner(client, "falso").plan("Salve a primeira vaga", "http://x")
    assert plan.attempts == 2 and len(plan.steps) == 2
    assert 'pede para "salvar", mas nenhum clique' in client.calls[1]["messages"][-1]["content"]


def test_plan_missing_the_request_value_goes_back_to_the_model():
    from anchor.planner import LLMPlanner
    bad = {"goals": [{"id": "g1", "description": "busca aberta", "conclusive": True}],
           "steps": [{"action": "click", "description": "Search /", "value": None, "goal": "g1", "expect": None}]}
    client = FakeClient(json.dumps(bad), json.dumps(bad))
    with pytest.raises(PlanError, match='menciona "Pi Network"'):
        LLMPlanner(client, "falso").plan("Pesquise a moeda Pi Network", "http://x")


def test_replanning_does_not_need_to_cover_the_whole_request():
    from anchor.planner import LLMPlanner
    remaining = {"goals": [], "steps": [{"action": "click", "description": "Salvar", "value": None,
                                         "goal": "g2", "expect": None}]}
    client = FakeClient(json.dumps(remaining))
    plan = LLMPlanner(client, "falso").plan("Cadastre a Maria Silva e salve", "http://x",
                                            history=["feito: fill Nome = \"Maria Silva\""], known_goals={"g1", "g2"})
    assert len(plan.steps) == 1


def test_value_with_brackets_copied_from_the_summary_is_cleaned():
    from anchor.planner.execute import clean_value
    assert clean_value("[Price: low to high]") == "Price: low to high"
    assert clean_value('[opções: Português]') == "Português"
    assert clean_value('"TI"') == "TI"
    assert clean_value("(92) 99999-0000") == "(92) 99999-0000"


def test_focus_only_click_does_not_fulfill_the_goal(page):
    page.set_content('<html><body><select aria-label="Sort by"><option>Featured</option>'
                     '<option>Price: low to high</option></select></body></html>')
    goals = [Goal("g1", "produtos ordenados", True)]
    planner = GoalPlanner((goals, [("click", "Sort by", None, "g1", None)]), ([], []))
    result = run(page, planner, request="ordene por preço")
    assert result.status == "cancelled" and "pending goals" in result.message



def test_goal_saying_save_without_a_saving_step_is_not_enough():
    from anchor.planner import check_request
    with pytest.raises(PlanError, match='pede para "salvar"'):
        check_request([Step("click", "Consultor RPA")], [Goal("g1", "vaga salva", True)], "Salve a primeira vaga")


def test_filling_the_search_is_not_searching():
    from anchor.planner import check_request
    with pytest.raises(PlanError, match='pede para "pesquisar"'):
        check_request([Step("fill", "Search /", "Pi Network")], [], "Pesquise a moeda Pi Network")
    check_request([Step("fill", "Search /", "Pi Network"), Step("press", "Search /", "Enter")], [],
                  "Pesquise a moeda Pi Network")   # with Enter, it passes


def test_effect_check_uses_the_cleaned_value(page):
    page.set_content('<html><body><select aria-label="Sort by"><option>Featured</option>'
                     '<option>Price: low to high</option></select></body></html>')
    goals = [Goal("g1", "produtos ordenados", True)]
    planner = GoalPlanner((goals, [("select", "Sort by", "[Price: low to high]", "g1", None)]), ([], []))
    result = run(page, planner, request="ordene por preço")
    assert result.ok and result.goals_done == 1


# --------------------------------------------------------------------------
# Before declaring success, what was DONE must cover the request
# --------------------------------------------------------------------------

POPUP_SEARCH = """<html><body>
  <div class="lupa" style="cursor:pointer" onclick="document.getElementById('b').hidden=false; document.getElementById('q').focus()">Search /</div>
  <div id="b" hidden role="dialog" style="position:fixed;inset:0;background:#fff">
    <label for="q">Search coins</label><input id="q"
      onkeydown="if(event.key==='Enter') document.getElementById('r').textContent='Resultados para ' + this.value">
    <p id="r"></p></div>
</body></html>"""

ONE_GOAL = [Goal("g1", "busca feita", True)]
FULL_SEARCH = [("click", "Search /", None, "g1", None), ("fill", "Search coins", "Pi Network", "g1", None),
               ("press", "Search coins", "Enter", "g1", None)]


def test_model_saying_it_is_done_too_early_gets_warned_and_finishes_the_search(page):
    page.set_content(POPUP_SEARCH)
    planner = GoalPlanner(
        (ONE_GOAL, FULL_SEARCH),
        ([], []),                       # the pop-up opened: "nothing is left" (wrong)
        ([], []),                       # end check: "nothing is left" (wrong again)
        ([], FULL_SEARCH[1:]),          # after the warning, it finishes the search
        ([], []),
    )
    result = run(page, planner, request="Pesquise a moeda Pi Network")
    assert result.ok and "Resultados para Pi Network" in page.inner_text("body")
    warned = planner.calls[3]["history"]
    assert any(h.startswith('o pedido ainda não foi cumprido: o pedido menciona "Pi Network"') for h in warned)


def test_model_insisting_it_is_done_ends_without_success(page):
    page.set_content(POPUP_SEARCH)
    planner = GoalPlanner((ONE_GOAL, FULL_SEARCH), ([], []), ([], []), ([], []), ([], []))
    result = run(page, planner, request="Pesquise a moeda Pi Network")
    assert result.status == "cancelled"
    assert result.message.startswith("the request was not fulfilled")
    assert "Pi Network" in result.message


def test_enter_in_any_field_counts_as_searching():
    from anchor.planner import check_request
    check_request([Step("fill", "Type a coin", "Pi Network"), Step("press", "Type a coin", "Enter")], [],
                  "Pesquise a moeda Pi Network")   # does not raise
