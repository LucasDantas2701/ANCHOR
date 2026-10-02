"""Tests of the evaluation of complete tasks (eval/plan_run.py), with a fake LLM."""

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


def test_model_plan_completes_the_task(page):
    client = FakeClient(as_json(TASK["reference"]))
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert r.success and r.plan_valid
    assert r.steps_ok == r.plan_steps == 2
    assert r.tokens_in == 100 and r.tokens_out == 20
    assert "Selecionar Ana Souza" in client.calls[0]["messages"][1]["content"]  # received the page


def test_wrong_plan_does_not_complete(page):
    # Covers the request (mentions Ana and Carla), but also checks Bruno.
    client = FakeClient(as_json([["check", "caixa Selecionar Ana Souza", None],
                                 ["check", "caixa Selecionar Carla Mendes", None],
                                 ["check", "caixa Selecionar Bruno Lima", None]]))
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert r.plan_valid and not r.success
    assert r.checks_ok < r.checks


def test_model_without_valid_answer_is_recorded(page):
    client = FakeClient("não sei", "também não")
    r = run_task(fresh(page), LLMPlanner(client, "falso"), "falso", TASK, use_page=True)
    assert not r.plan_valid and not r.success
    assert "PlanError" in r.error
    s = summarize([r])
    assert s["plan_valid"] == 0 and s["success"] == 0


TASKS_ALL = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
FILTER_TASK = next(t for t in TASKS_ALL if t["id"] == "p-usr-01")


def test_unrequested_step_is_counted(page):
    plan = [["select", "Filtrar por status", "Inativos"], ["click", "Exportar planilha", None]]
    r = run_task(fresh(page), LLMPlanner(FakeClient(as_json(plan)), "falso"), "falso", FILTER_TASK, use_page=True)
    assert r.success                      # what was requested happened...
    assert not r.clean                    # ...but with an extra action
    assert r.unrequested == 1
    assert "Exportar planilha" in r.unrequested_list
    s = summarize([r])
    assert s["success"] == 1 and s["clean"] == 0 and s["unrequested"] == 1


def test_plan_without_extra_steps_is_clean(page):
    plan = [["select", "Filtrar por status", "Inativos"]]
    r = run_task(fresh(page), LLMPlanner(FakeClient(as_json(plan)), "falso"), "falso", FILTER_TASK, use_page=True)
    assert r.success and r.clean and r.unrequested == 0


def test_check_points_out_tasks_with_problems(capsys, browser):
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


def test_agent_mode_checks_the_end_and_counts_the_calls(page):
    from eval.plan_run import run_task_agent
    plan = as_json([["select", "Filtrar por status", "Inativos"]])
    client = FakeClient(plan, as_json([]))          # plan + end check (nothing left)
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert r.success and r.clean
    assert r.llm_calls == 2 and r.replans == 0
    assert r.tokens_in == 200
    assert "O que já aconteceu" in client.calls[1]["messages"][1]["content"]


def test_premature_end_is_counted(page):
    from eval.plan_run import run_task_agent

    # The plan mentions Carla, but only hovers over her and declares the end: the
    # task's checks fail (and the check of the plan against the request does not catch it).
    task = next(t for t in TASKS_ALL if t["id"] == "p-usr-02")
    client = FakeClient(as_json([["check", "Selecionar Ana Souza", None],
                                 ["hover", "Selecionar Carla Mendes", None]]), as_json([]))
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", task)
    assert r.premature and not r.success
    s = summarize([r])
    assert s["premature"] == 1


def test_agent_mode_records_goals_and_suspicions(page):
    from eval.plan_run import run_task_agent
    plan = {"goals": [{"id": "g1", "description": "inativos filtrados", "conclusive": True}],
            "steps": [{"action": "select", "description": "Filtrar por status", "value": "Inativos",
                       "goal": "g1", "expect": "Mostrando 1 usuário inativo"}]}
    client = FakeClient(json.dumps(plan), json.dumps({"goals": [], "steps": []}))
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert r.success and r.goals == 1 and r.goals_done == 1
    assert r.suspicions == 1                    # the test page does not show this text


def test_agent_mode_flags_invalid_plan_in_any_language(page):
    from eval.plan_run import run_task_agent
    client = FakeClient("isto não é JSON", "nem isto")
    r = run_task_agent(fresh(page), LLMPlanner(client, "falso"), "falso", FILTER_TASK)
    assert not r.plan_valid and not r.success


def test_english_tasks_are_loaded_with_their_language():
    from eval.plan_run import load_tasks
    tasks = load_tasks()
    english = [t for t in tasks if t.get("language") == "en"]
    assert len(english) == 15 and all(t["id"].startswith("en-") for t in english)
