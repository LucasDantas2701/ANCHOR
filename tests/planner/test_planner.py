"""
Tests of the planner with a fake client (no real API calls).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx2
import openai
import pytest

from anchor.engine.action_executor import ActionExecutor
from anchor.planner import (
    ConfigError,
    LLMPlanner,
    LLMProfile,
    PlanError,
    Step,
    parse_plan,
    run_plan,
)
from anchor.planner.plan import Plan
from anchor.planner.prompt import user_message

CADASTRO = (Path(__file__).resolve().parents[2] / "eval" / "fixtures" / "registration.html").as_uri()


class FakeClient:
    """Imitates client.chat.completions.create, returning ready-made answers."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def plan_json(*steps):
    return json.dumps({"steps": [dict(action=a, description=d, value=v) for a, d, v in steps]})


GOOD = plan_json(("fill", "campo Nome completo", "Maria Silva"), ("click", "botão Salvar cadastro", None))


def test_valid_plan():
    client = FakeClient(GOOD)
    plan = LLMPlanner(client, "modelo-x").plan("cadastre a Maria", "http://x", ["Campo de texto \"Nome completo\""])
    assert [s.action for s in plan.steps] == ["fill", "click"]
    assert plan.steps[0].value == "Maria Silva"
    assert plan.attempts == 1 and plan.tokens_in == 100 and plan.tokens_out == 20
    sent = client.calls[0]
    assert sent["model"] == "modelo-x" and sent["temperature"] == 0.0
    assert sent["response_format"]["type"] == "json_schema"
    assert "Nome completo" in sent["messages"][1]["content"]


def test_invalid_plan_gets_the_error_and_is_fixed():
    bad = plan_json(("fill", "campo Nome", None))  # fill without a value
    client = FakeClient(bad, GOOD)
    plan = LLMPlanner(client, "m").plan("cadastre a Maria", "http://x")
    assert plan.attempts == 2 and plan.tokens_in == 200
    feedback = client.calls[1]["messages"][-1]["content"]
    assert "precisa de um valor" in feedback


def test_gives_up_after_the_attempts():
    client = FakeClient("isso não é json", "nem isso")
    with pytest.raises(PlanError, match="2 attempts"):
        LLMPlanner(client, "m").plan("x", "http://x")


def test_accepts_json_inside_a_code_block():
    client = FakeClient("Claro! Aqui está:\n```json\n" + GOOD + "\n```")
    assert len(LLMPlanner(client, "m").plan("x", "http://x").steps) == 2


def test_ignores_the_reasoning_of_thinking_models():
    client = FakeClient("<think>O usuário quer cadastrar... vou usar fill.</think>\n" + GOOD)
    assert len(LLMPlanner(client, "m").plan("x", "http://x").steps) == 2


def test_profile_extra_parameters_go_to_the_server():
    client = FakeClient(GOOD)
    LLMPlanner(client, "m", extra_body={"opcao": False}).plan("x", "http://x")
    assert client.calls[0]["extra_body"] == {"opcao": False}


def test_without_extra_parameters_nothing_is_sent():
    client = FakeClient(GOOD)
    LLMPlanner(client, "m").plan("x", "http://x")
    assert "extra_body" not in client.calls[0]


def test_server_without_json_schema_uses_plain_json():
    request = httpx2.Request("POST", "http://localhost/v1/chat/completions")
    no_schema = openai.BadRequestError("json_schema não suportado",
                                       response=httpx2.Response(400, request=request), body=None)
    client = FakeClient(no_schema, GOOD)
    plan = LLMPlanner(client, "m").plan("x", "http://x")
    assert len(plan.steps) == 2
    assert client.calls[1]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("data, message", [
    ({"passos": []}, "steps"),
    ({"steps": [{"action": "navigate", "description": "x", "value": None}]}, "não existe"),
    ({"steps": [{"action": "click", "description": "  ", "value": None}]}, "descrição vazia"),
    ({"steps": [{"action": "select", "description": "lista", "value": ""}]}, "precisa de um valor"),
])
def test_plan_validation(data, message):
    with pytest.raises(PlanError, match=message):
        parse_plan(data)


def test_empty_plan_is_valid():
    assert parse_plan({"steps": []}) == []


def test_message_without_list_of_elements():
    msg = user_message("abrir o carrinho", "http://x", None)
    assert "Pedido do usuário: abrir o carrinho" in msg and "Elementos" not in msg


def test_profile_without_key_explains_how_to_configure(monkeypatch):
    monkeypatch.delenv("CHAVE_DE_TESTE", raising=False)
    profile = LLMProfile(name="p", model="m", api_key_env="CHAVE_DE_TESTE")
    with pytest.raises(ConfigError, match="setx CHAVE_DE_TESTE"):
        profile.client()


def test_profile_with_model_not_filled_in():
    with pytest.raises(ConfigError, match='"model" field'):
        LLMProfile(name="p", model="COLOQUE_O_MODELO").client()


def test_local_profile_does_not_require_a_key():
    client = LLMProfile(name="p", model="m", base_url="http://localhost:11434/v1").client()
    assert str(client.base_url).startswith("http://localhost:11434")


def test_plan_run_on_the_form(page):
    page.goto(CADASTRO)
    plan = Plan(steps=[
        Step("fill", "campo Nome completo", "Maria Silva"),
        Step("fill", "campo CPF", "123.456.789-00"),
        Step("select", "lista Departamento", "TI"),
        Step("check", "opção PJ", None),
        Step("check", "caixa Li e aceito os termos de uso", None),
    ])
    results = run_plan(ActionExecutor(page), plan)
    assert [r.status for _, r in results] == ["success"] * 5
    assert page.input_value("#nome") == "Maria Silva"
    assert page.input_value("#cpf") == "123.456.789-00"
    assert page.eval_on_selector("#dep", "e => e.selectedOptions[0].text") == "TI"
    assert page.is_checked("input[value=pj]") and page.is_checked("#termos")


def test_execution_stops_at_the_first_failing_step(page):
    page.goto(CADASTRO)
    plan = Plan(steps=[Step("click", "botão Enviar para o espaço sideral", None),
                       Step("fill", "campo Nome completo", "Maria")])
    results = run_plan(ActionExecutor(page), plan)
    assert len(results) == 1 and results[0][1].status != "success"
    assert page.input_value("#nome") == ""


@pytest.mark.parametrize("raw, clean", [
    ('Campo de texto "Nome completo"', "Nome completo"),
    ("Caixa de marcação Remember me", "Remember me"),
    ("Lista de opções Sort by", "Sort by"),
    ("campo de busca Search products", "Search products"),
    ('Botão "Add to cart" (UltraBook 14)', "Botão Add to cart (UltraBook 14)"),
    ("Opção PJ", "Opção PJ"),
    ("Salvar cadastro", "Salvar cadastro"),
])
def test_description_cleanup(raw, clean):
    from anchor.planner.execute import clean_description
    assert clean_description(raw) == clean


def test_description_with_kind_label_is_not_ambiguous(page):
    page.goto(CADASTRO)
    plan = Plan(steps=[Step("fill", "Campo de texto Telefone", "(92) 99999-0000")])
    results = run_plan(ActionExecutor(page), plan)
    assert results[0][1].status == "success"
    assert page.input_value("#tel") == "(92) 99999-0000"


def test_select_on_a_radio_button_becomes_check(page):
    page.goto(CADASTRO)
    results = run_plan(ActionExecutor(page), Plan(steps=[Step("select", "Opção PJ", "PJ")]))
    assert results[0][1].status == "success"
    assert page.is_checked("input[value=pj]")


def test_summary_guided_by_the_request_brings_the_relevant_element(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    links = "".join(f'<a href="/c/{i}">Categoria {i}</a> ' for i in range(90))
    page.set_content(f'<html><body>{links}<div style="cursor:pointer">Search /</div></body></html>')
    without = page_elements(ElementResolver(page))
    with_request = page_elements(ElementResolver(page), request="pesquise a moeda Pi Network")
    assert not any("Search /" in line for line in without)          # cut by the limit of 80
    assert with_request[0].startswith('Área clicável "Search /"')   # guided by the request
