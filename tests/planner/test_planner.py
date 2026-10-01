"""
Testes do planejador com um cliente falso (nenhuma chamada real à API).
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
    """Imita client.chat.completions.create devolvendo respostas prontas."""

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


def test_plano_valido():
    client = FakeClient(GOOD)
    plan = LLMPlanner(client, "modelo-x").plan("cadastre a Maria", "http://x", ["Campo de texto \"Nome completo\""])
    assert [s.action for s in plan.steps] == ["fill", "click"]
    assert plan.steps[0].value == "Maria Silva"
    assert plan.attempts == 1 and plan.tokens_in == 100 and plan.tokens_out == 20
    sent = client.calls[0]
    assert sent["model"] == "modelo-x" and sent["temperature"] == 0.0
    assert sent["response_format"]["type"] == "json_schema"
    assert "Nome completo" in sent["messages"][1]["content"]


def test_plano_invalido_recebe_o_erro_e_corrige():
    bad = plan_json(("fill", "campo Nome", None))  # fill sem valor
    client = FakeClient(bad, GOOD)
    plan = LLMPlanner(client, "m").plan("cadastre a Maria", "http://x")
    assert plan.attempts == 2 and plan.tokens_in == 200
    feedback = client.calls[1]["messages"][-1]["content"]
    assert "precisa de um valor" in feedback


def test_desiste_depois_das_tentativas():
    client = FakeClient("isso não é json", "nem isso")
    with pytest.raises(PlanError, match="2 attempts"):
        LLMPlanner(client, "m").plan("x", "http://x")


def test_aceita_json_dentro_de_bloco_de_codigo():
    client = FakeClient("Claro! Aqui está:\n```json\n" + GOOD + "\n```")
    assert len(LLMPlanner(client, "m").plan("x", "http://x").steps) == 2


def test_ignora_o_raciocinio_de_modelos_thinking():
    client = FakeClient("<think>O usuário quer cadastrar... vou usar fill.</think>\n" + GOOD)
    assert len(LLMPlanner(client, "m").plan("x", "http://x").steps) == 2


def test_parametros_extras_do_perfil_vao_para_o_servidor():
    client = FakeClient(GOOD)
    LLMPlanner(client, "m", extra_body={"opcao": False}).plan("x", "http://x")
    assert client.calls[0]["extra_body"] == {"opcao": False}


def test_sem_parametros_extras_nada_e_enviado():
    client = FakeClient(GOOD)
    LLMPlanner(client, "m").plan("x", "http://x")
    assert "extra_body" not in client.calls[0]


def test_servidor_sem_esquema_json_usa_json_simples():
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
def test_validacao_do_plano(data, message):
    with pytest.raises(PlanError, match=message):
        parse_plan(data)


def test_plano_vazio_e_valido():
    assert parse_plan({"steps": []}) == []


def test_mensagem_sem_lista_de_elementos():
    msg = user_message("abrir o carrinho", "http://x", None)
    assert "Pedido do usuário: abrir o carrinho" in msg and "Elementos" not in msg


def test_perfil_sem_chave_explica_como_configurar(monkeypatch):
    monkeypatch.delenv("CHAVE_DE_TESTE", raising=False)
    profile = LLMProfile(name="p", model="m", api_key_env="CHAVE_DE_TESTE")
    with pytest.raises(ConfigError, match="setx CHAVE_DE_TESTE"):
        profile.client()


def test_perfil_com_modelo_nao_preenchido():
    with pytest.raises(ConfigError, match='"model" field'):
        LLMProfile(name="p", model="COLOQUE_O_MODELO").client()


def test_perfil_local_nao_exige_chave():
    client = LLMProfile(name="p", model="m", base_url="http://localhost:11434/v1").client()
    assert str(client.base_url).startswith("http://localhost:11434")


def test_plano_executado_no_formulario(page):
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


def test_execucao_para_no_primeiro_passo_que_falha(page):
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
def test_limpeza_da_descricao(raw, clean):
    from anchor.planner.execute import clean_description
    assert clean_description(raw) == clean


def test_descricao_com_rotulo_de_tipo_nao_fica_ambigua(page):
    page.goto(CADASTRO)
    plan = Plan(steps=[Step("fill", "Campo de texto Telefone", "(92) 99999-0000")])
    results = run_plan(ActionExecutor(page), plan)
    assert results[0][1].status == "success"
    assert page.input_value("#tel") == "(92) 99999-0000"


def test_select_em_botao_de_opcao_vira_check(page):
    page.goto(CADASTRO)
    results = run_plan(ActionExecutor(page), Plan(steps=[Step("select", "Opção PJ", "PJ")]))
    assert results[0][1].status == "success"
    assert page.is_checked("input[value=pj]")


def test_resumo_guiado_pelo_pedido_traz_o_elemento_relevante(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    links = "".join(f'<a href="/c/{i}">Categoria {i}</a> ' for i in range(90))
    page.set_content(f'<html><body>{links}<div style="cursor:pointer">Search /</div></body></html>')
    without = page_elements(ElementResolver(page))
    with_request = page_elements(ElementResolver(page), request="pesquise a moeda Pi Network")
    assert not any("Search /" in line for line in without)          # cortado pelo limite de 80
    assert with_request[0].startswith('Área clicável "Search /"')   # guiado pelo pedido
