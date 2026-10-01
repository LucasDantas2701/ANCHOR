"""Testes da avaliação de tarefas completas (eval/plan_run.py), com LLM falso."""

import json

from anchor.planner import LLMPlanner
from eval.plan_run import INSTRUMENT, TASKS, run_task, summarize
from tests.planner.test_planner import FakeClient

TASK = next(t for t in json.loads(TASKS.read_text(encoding="utf-8"))["tasks"] if t["id"] == "p-usr-02")


def as_json(steps):
    return json.dumps({"steps": [dict(action=a, description=d, value=v) for a, d, v in steps]})


def fresh(page):
    page.set_default_timeout(3000)
    page.add_init_script(INSTRUMENT)
    return page


def test_plano_do_modelo_cumpre_a_tarefa(page):
    client = FakeClient(as_json(TASK["reference"]))
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert r.sucesso and r.plano_valido
    assert r.passos_ok == r.passos_plano == 2
    assert r.tokens_entrada == 100 and r.tokens_saida == 20
    assert "Selecionar Ana Souza" in client.calls[0]["messages"][1]["content"]  # recebeu a página


def test_plano_errado_nao_cumpre(page):
    # Cobre o pedido (cita a Ana e a Carla), mas também marca o Bruno.
    client = FakeClient(as_json([["check", "caixa Selecionar Ana Souza", None],
                                 ["check", "caixa Selecionar Carla Mendes", None],
                                 ["check", "caixa Selecionar Bruno Lima", None]]))
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert r.plano_valido and not r.sucesso
    assert r.verificacoes_ok < r.verificacoes


def test_modelo_sem_resposta_valida_e_registrado(page):
    client = FakeClient("não sei", "também não")
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert not r.plano_valido and not r.sucesso
    assert "PlanError" in r.erro
    s = summarize([r])
    assert s["plano_valido"] == 0 and s["sucesso"] == 0


TASKS_ALL = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
FILTER_TASK = next(t for t in TASKS_ALL if t["id"] == "p-usr-01")


def test_passo_nao_pedido_e_contado(page):
    plan = [["select", "Filtrar por status", "Inativos"], ["click", "Exportar planilha", None]]
    r = run_task(fresh(page), LLMPlanner(FakeClient(as_json(plan)), "falso"), "falso", FILTER_TASK, use_page=True)
    assert r.sucesso                      # o que foi pedido aconteceu...
    assert not r.limpa                    # ...mas com uma ação a mais
    assert r.nao_pedidos == 1
    assert "Exportar planilha" in r.nao_pedidos_lista
    s = summarize([r])
    assert s["sucesso"] == 1 and s["limpas"] == 0 and s["nao_pedidos"] == 1


def test_plano_sem_passos_a_mais_e_limpo(page):
    plan = [["select", "Filtrar por status", "Inativos"]]
    r = run_task(fresh(page), LLMPlanner(FakeClient(as_json(plan)), "falso"), "falso", FILTER_TASK, use_page=True)
    assert r.sucesso and r.limpa and r.nao_pedidos == 0


def test_check_aponta_tarefas_com_problema(capsys, browser):
    from eval.plan_run import check_tasks
    ok = dict(FILTER_TASK)
    bad = [
        {**ok, "id": "sem-campos", "allowed": []},
        {**ok, "id": "pagina-inexistente", "fixture": "nao_existe.html"},
        {**ok, "id": "verificacao-com-erro", "checks": ["document.querySelector('#x').value === 1"]},
    ]
    assert check_tasks([ok], browser) == 0
    assert check_tasks(bad, browser) == 1
    out = capsys.readouterr().out
    for name in ("sem-campos", "pagina-inexistente", "verificacao-com-erro"):
        assert name in out


def test_modo_agente_confere_o_fim_e_conta_as_chamadas(page):
    from eval.plan_run import run_task_agent
    plan = as_json([["select", "Filtrar por status", "Inativos"]])
    client = FakeClient(plan, as_json([]))          # plano + conferência do fim (nada falta)
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert r.sucesso and r.limpa
    assert r.chamadas_llm == 2 and r.replanejamentos == 0
    assert r.tokens_entrada == 200
    assert "O que já aconteceu" in client.calls[1]["messages"][1]["content"]


def test_termino_prematuro_e_contado(page):
    from eval.plan_run import run_task_agent

    # O plano cita a Carla, mas só passa o mouse sobre ela e declara o fim: as
    # verificações da tarefa falham (e a conferência do plano contra o pedido não pega isso).
    task = next(t for t in TASKS_ALL if t["id"] == "p-usr-02")
    client = FakeClient(as_json([["check", "Selecionar Ana Souza", None],
                                 ["hover", "Selecionar Carla Mendes", None]]), as_json([]))
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", task)
    assert r.prematuro and not r.sucesso
    s = summarize([r])
    assert s["prematuros"] == 1


def test_modo_agente_registra_metas_e_suspeitas(page):
    from eval.plan_run import run_task_agent
    plan = {"goals": [{"id": "g1", "description": "inativos filtrados", "conclusive": True}],
            "steps": [{"action": "select", "description": "Filtrar por status", "value": "Inativos",
                       "goal": "g1", "expect": "Mostrando 1 usuário inativo"}]}
    client = FakeClient(json.dumps(plan), json.dumps({"goals": [], "steps": []}))
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert r.sucesso and r.metas == 1 and r.metas_cumpridas == 1
    assert r.suspeitas == 1                    # a página de teste não mostra esse texto


def test_modo_agente_marca_plano_invalido_em_qualquer_idioma(page):
    from eval.plan_run import run_task_agent
    client = FakeClient("isto não é JSON", "nem isto")
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert not r.plano_valido and not r.sucesso
