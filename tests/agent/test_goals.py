"""
Metas (checkpoints) e efeito esperado: o fim só é declarado com todas as
metas cumpridas, e um texto esperado que não aparece vira suspeita.
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
    """Devolve planos prontos (com metas) e guarda o histórico que recebeu."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), []

    def plan(self, request, url, page_elements=None, history=None, known_goals=None):
        self.calls.append({"history": list(history or []), "known": set(known_goals or [])})
        goals, steps = self.plans.pop(0) if self.plans else ([], [])
        return Plan(steps=[Step(*s) for s in steps], goals=goals)


def run(page, planner, request="cadastre a Maria"):
    page.set_default_timeout(1500)
    return Agent(page, planner, ActionExecutor(page), report=None).run(request)


FULL = [("fill", "Nome", "Maria", "g1", None), ("fill", "E-mail", "m@x.com", "g2", None),
        ("click", "Salvar", None, "g3", "Cadastro salvo")]


def test_todas_as_metas_cumpridas(page):
    page.set_content(FORM)
    planner = GoalPlanner((G, FULL), ([], []))
    result = run(page, planner)
    assert result.ok and result.goals_total == 3 and result.goals_done == 3
    assert result.suspicions == 0
    end_check = planner.calls[1]["history"]
    assert any(line.startswith("metas: g1 (nome preenchido): cumprida") for line in end_check)
    assert any("mensagens visíveis na página agora" in line and "Cadastro salvo" in line for line in end_check)


def test_fim_com_meta_pendente_nao_e_sucesso(page):
    page.set_content(FORM)
    planner = GoalPlanner((G, FULL[:2]), ([], []))     # o modelo "esquece" de salvar e diz que acabou
    result = run(page, planner)
    assert result.status == "cancelled"
    assert "pending goals: g3 (cadastro salvo)" in result.message


def test_texto_esperado_que_nao_aparece_e_suspeita_nao_falha(page):
    page.set_content(FORM.replace("Cadastro salvo", "Pronto"))
    planner = GoalPlanner((G, FULL), ([], []))
    result = run(page, planner)
    assert result.ok and result.suspicions == 1
    assert "expected to see" in result.records[2].note
    assert any(h.startswith("suspeita:") for h in planner.calls[1]["history"])


def test_meta_so_com_acao_destrutiva_barrada_e_descartada(page):
    page.set_content("""<html><body>
      <button onclick="document.body.dataset.f=1">Fechar vaga</button>
      <button onclick="document.getElementById('m').textContent='Vaga salva'">Salvar vaga</button>
      <p id="m" role="status"></p></body></html>""")
    goals = [Goal("g1", "vaga fechada"), Goal("g2", "vaga salva", True)]
    steps = [("click", "Fechar vaga", None, "g1", None), ("click", "Salvar vaga", None, "g2", None)]
    result = run(page, GoalPlanner((goals, steps), ([], [])), request="salve a vaga")
    assert result.ok and result.goals_done == 1
    assert result.records[0].status == "blocked"


def test_replanejamento_usa_as_metas_ja_conhecidas(page):
    page.set_content(FORM)
    first = {"goals": [{"id": "g1", "description": "nome", "conclusive": False},
                       {"id": "g2", "description": "salvo", "conclusive": True}],
             "steps": [{"action": "fill", "description": "Campo que não existe", "value": "Maria",
                        "goal": "g1", "expect": None},
                       {"action": "click", "description": "Salvar", "value": None,
                        "goal": "g2", "expect": None}]}
    # O replanejamento cita "g2" sem repetir a lista de metas: precisa ser aceito.
    replan = {"goals": [], "steps": [{"action": "fill", "description": "Nome", "value": "Maria",
                                      "goal": "g1", "expect": None},
                                     {"action": "click", "description": "Salvar", "value": None,
                                      "goal": "g2", "expect": None}]}
    end = {"goals": [], "steps": []}
    client = FakeClient(json.dumps(first), json.dumps(replan), json.dumps(end))
    result = run(page, LLMPlanner(client, "falso"))
    assert result.ok and result.goals_done == 2


def test_meta_inexistente_no_passo_e_rejeitada():
    from anchor.planner import check_goals
    with pytest.raises(PlanError, match='a meta "g9" não existe'):
        check_goals([Step("click", "Salvar", None, "g9")], [Goal("g1", "x", True)])


def test_meta_conclusiva_precisa_vir_por_ultimo():
    from anchor.planner import check_goals
    steps = [Step("click", "Salvar", None, "g2"), Step("fill", "Nome", "Ana", "g1")]
    with pytest.raises(PlanError, match="devem vir por último"):
        check_goals(steps, [Goal("g1", "nome"), Goal("g2", "salvo", True)])


def test_plano_sem_metas_continua_valido():
    from anchor.planner import check_goals
    check_goals([Step("click", "Salvar")], [])        # não lança



def test_meta_sem_passos_e_rejeitada_no_plano():
    from anchor.planner import check_goals
    goals = [Goal("g1", "busca feita", True), Goal("g2", "resultado exibido")]
    with pytest.raises(PlanError, match="g2 não tem nenhum"):
        check_goals([Step("click", "Search", None, "g1")], goals)


def test_plano_sem_meta_conclusiva_e_rejeitado():
    from anchor.planner import check_goals
    with pytest.raises(PlanError, match="conclusiva"):
        check_goals([Step("click", "Consultor RPA", None, "g1")], [Goal("g1", "vaga aberta")])


def test_meta_abandonada_pelo_replanejamento_e_substituida(page):
    page.set_content("""<html><body>
      <select aria-label="Sort by"><option>Featured</option><option>Price: low to high</option></select>
      <button>Botão parado</button></body></html>""")
    goals = [Goal("g1", "lista aberta"), Goal("g2", "produtos ordenados", True)]
    planner = GoalPlanner(
        (goals, [("click", "Botão parado", None, "g1", None)]),          # sem efeito: falha
        ([], [("select", "Sort by", "Price: low to high", "g2", None)]),  # outro caminho, sem g1
        ([], []),
    )
    result = run(page, planner, request="ordene por preço")
    assert result.ok and result.goals_done == 1


def test_clicar_numa_caixa_de_marcacao_confere_o_estado(page):
    page.set_content('<html><body><label><input type="checkbox" id="c"> Selecionar Ana</label></body></html>')
    goals = [Goal("g1", "Ana selecionada", True)]
    result = run(page, GoalPlanner((goals, [("click", "Selecionar Ana", None, "g1", None)]), ([], [])))
    assert result.ok and result.no_effect == 0 and page.is_checked("#c")


def test_enter_no_elemento_errado_vai_para_o_ultimo_campo(page):
    page.set_content("""<html><body><div class="lupa" style="cursor:pointer">Search /</div>
      <label for="q">Coins</label><input id="q"
        onkeydown="if(event.key==='Enter'){document.getElementById('r').textContent='Resultados'}">
      <p id="r"></p></body></html>""")
    goals = [Goal("g1", "busca feita", True)]
    steps = [("fill", "Coins", "pi", "g1", None), ("press", "Search /", "Enter", "g1", None)]
    result = run(page, GoalPlanner((goals, steps), ([], [])), request="pesquise pi")
    assert result.ok and result.records[1].resolved_by == "enter_in_field"


# --------------------------------------------------------------------------
# O plano cobre o pedido? (conferido no plano inicial)
# --------------------------------------------------------------------------

def test_plano_sem_o_verbo_do_pedido_volta_ao_modelo():
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


def test_plano_sem_o_valor_do_pedido_volta_ao_modelo():
    from anchor.planner import LLMPlanner
    bad = {"goals": [{"id": "g1", "description": "busca aberta", "conclusive": True}],
           "steps": [{"action": "click", "description": "Search /", "value": None, "goal": "g1", "expect": None}]}
    client = FakeClient(json.dumps(bad), json.dumps(bad))
    with pytest.raises(PlanError, match='menciona "Pi Network"'):
        LLMPlanner(client, "falso").plan("Pesquise a moeda Pi Network", "http://x")


def test_replanejamento_nao_precisa_repetir_o_pedido_todo():
    from anchor.planner import LLMPlanner
    remaining = {"goals": [], "steps": [{"action": "click", "description": "Salvar", "value": None,
                                         "goal": "g2", "expect": None}]}
    client = FakeClient(json.dumps(remaining))
    plan = LLMPlanner(client, "falso").plan("Cadastre a Maria Silva e salve", "http://x",
                                            history=["feito: fill Nome = \"Maria Silva\""], known_goals={"g1", "g2"})
    assert len(plan.steps) == 1


def test_valor_com_colchetes_copiado_do_resumo_e_limpo():
    from anchor.planner.execute import clean_value
    assert clean_value("[Price: low to high]") == "Price: low to high"
    assert clean_value('[opções: Português]') == "Português"
    assert clean_value('"TI"') == "TI"
    assert clean_value("(92) 99999-0000") == "(92) 99999-0000"


def test_clique_de_foco_nao_cumpre_a_meta(page):
    page.set_content('<html><body><select aria-label="Sort by"><option>Featured</option>'
                     '<option>Price: low to high</option></select></body></html>')
    goals = [Goal("g1", "produtos ordenados", True)]
    planner = GoalPlanner((goals, [("click", "Sort by", None, "g1", None)]), ([], []))
    result = run(page, planner, request="ordene por preço")
    assert result.status == "cancelled" and "pending goals" in result.message



def test_meta_que_fala_em_salvar_sem_passo_que_salve_nao_basta():
    from anchor.planner import check_request
    with pytest.raises(PlanError, match='pede para "salvar"'):
        check_request([Step("click", "Consultor RPA")], [Goal("g1", "vaga salva", True)], "Salve a primeira vaga")


def test_preencher_a_busca_nao_e_pesquisar():
    from anchor.planner import check_request
    with pytest.raises(PlanError, match='pede para "pesquisar"'):
        check_request([Step("fill", "Search /", "Pi Network")], [], "Pesquise a moeda Pi Network")
    check_request([Step("fill", "Search /", "Pi Network"), Step("press", "Search /", "Enter")], [],
                  "Pesquise a moeda Pi Network")   # com o Enter, passa


def test_verificacao_usa_o_valor_limpo(page):
    page.set_content('<html><body><select aria-label="Sort by"><option>Featured</option>'
                     '<option>Price: low to high</option></select></body></html>')
    goals = [Goal("g1", "produtos ordenados", True)]
    planner = GoalPlanner((goals, [("select", "Sort by", "[Price: low to high]", "g1", None)]), ([], []))
    result = run(page, planner, request="ordene por preço")
    assert result.ok and result.goals_done == 1
