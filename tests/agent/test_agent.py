"""
Testes do loop do agente, com um planejador roteirizado (planos prontos,
em sequência) e páginas de teste reais.
"""

from pathlib import Path

import pytest

from app.agent import Agent
from app.engine.action_executor import ActionExecutor
from app.planner import Plan, PlanError, Step


class ScriptedPlanner:
    """Devolve os planos da lista, um por chamada, e guarda o que recebeu."""

    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls = []

    def plan(self, request, url, page_elements=None, history=None):
        self.calls.append({"url": url, "elements": page_elements or [], "history": list(history or [])})
        if not self.plans:
            raise AssertionError("o agente pediu mais planos do que o roteiro previa")
        item = self.plans.pop(0)
        if isinstance(item, Exception):
            raise item
        return Plan(steps=[Step(a, d, v) for a, d, v in item], tokens_in=100, tokens_out=20)


FORM = """<html><body>
  <label for="nome">Nome</label><input id="nome">
  <label for="mail">E-mail</label><input id="mail" type="email">
  <button id="salvar" onclick="window.salvo=true">Salvar</button>
</body></html>"""


def run(page, planner, **kwargs):
    page.set_default_timeout(1500)
    return Agent(page, planner, ActionExecutor(page), report=None, **kwargs).run("cadastre a Maria")


def test_executa_o_plano_e_confere_o_fim(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria"), ("fill", "E-mail", "maria@x.com"), ("click", "Salvar", None)],
        [],  # conferência do fim: nada falta
    )
    result = run(page, planner)

    assert result.ok and result.message == "objetivo atingido"
    assert page.input_value("#nome") == "Maria" and page.evaluate("window.salvo") is True
    assert result.llm_calls == 2 and result.replans == 0 and result.failures == 0
    assert result.tokens_in == 200 and result.tokens_out == 40
    assert "feito: click Salvar" in planner.calls[1]["history"][-1]


def test_conferencia_do_fim_completa_o_que_faltou(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria")],
        [("click", "Salvar", None)],   # a conferência encontrou um passo faltando
        [],
    )
    result = run(page, planner)
    assert result.ok and page.evaluate("window.salvo") is True
    assert result.llm_calls == 3 and result.replans == 1


def test_sem_conferencia_do_fim(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([("fill", "Nome", "Maria")]), verify_end=False)
    assert result.ok and result.llm_calls == 1


def test_navegacao_leva_ao_replanejamento_com_a_pagina_nova(page, tmp_path: Path):
    (tmp_path / "passo2.html").write_text(
        '<html><body><label for="cpf">CPF</label><input id="cpf">'
        '<button onclick="window.enviado=true">Enviar</button></body></html>', encoding="utf-8")
    (tmp_path / "passo1.html").write_text(
        '<html><body><label for="nome">Nome</label><input id="nome">'
        '<a href="passo2.html">Próximo</a></body></html>', encoding="utf-8")
    page.goto((tmp_path / "passo1.html").as_uri())

    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria"), ("click", "Próximo", None), ("fill", "passo que não existe mais", "x")],
        [("fill", "CPF", "123"), ("click", "Enviar", None)],   # replanejado na página nova
        [],
    )
    result = run(page, planner)

    assert result.ok
    assert page.url.endswith("passo2.html") and page.input_value("#cpf") == "123"
    replan = planner.calls[1]
    assert replan["url"].endswith("passo2.html")
    assert any("CPF" in e for e in replan["elements"])            # recebeu os elementos da página nova
    assert replan["history"] == ["feito: fill Nome = \"Maria\"", "feito: click Próximo"]
    assert result.replans == 1


def test_falha_leva_ao_replanejamento_com_o_motivo(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("click", "Enviar para o espaço sideral", None)],
        [("click", "Salvar", None)],
        [],
    )
    result = run(page, planner)

    assert result.ok and result.failures == 1 and result.replans == 1
    assert result.records[0].status == "not_found"
    history = planner.calls[1]["history"]
    assert history[0].startswith("falhou: click Enviar para o espaço sideral")
    assert "nenhum elemento" in history[0]


def test_tres_falhas_cancelam_e_relatam(page):
    page.set_content(FORM)
    bad = [("click", "Botão que não existe", None)]
    result = run(page, ScriptedPlanner(bad, bad, bad))

    assert result.status == "cancelled" and result.failures == 3
    assert "3 tentativas sem sucesso" in result.message
    assert "Botão que não existe" in result.message


def test_modal_cobrindo_o_botao_e_fechado_no_replanejamento(page):
    page.set_content("""<html><body>
      <button id="salvar" onclick="window.salvo=true">Salvar</button>
      <div id="modal" style="position:fixed;inset:0;background:#fff">
        <p>Aceite os cookies</p>
        <button onclick="document.getElementById('modal').remove()">Fechar aviso</button>
      </div></body></html>""")
    planner = ScriptedPlanner(
        [("click", "Salvar", None)],
        [("click", "Fechar aviso", None), ("click", "Salvar", None)],
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.salvo") is True
    assert "coberto por outro" in planner.calls[1]["history"][0]


def test_plano_vazio_no_inicio_cancela(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([]))
    assert result.status == "cancelled" and "não pode ser feito" in result.message


def test_replanejamento_sem_saida_cancela(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([("click", "Botão que não existe", None)], []))
    assert result.status == "cancelled" and "não encontrou outro caminho" in result.message


def test_erro_do_modelo_encerra_com_mensagem(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner(PlanError("resposta inválida")))
    assert result.status == "failed" and "resposta inválida" in result.message


def test_limite_de_passos(page):
    page.set_content(FORM)
    loop = [("fill", "Nome", "Maria")] * 10
    result = run(page, ScriptedPlanner(loop), max_steps=4)
    assert result.status == "failed" and "limite de 4 passos" in result.message


class ChooseSecond:
    def choose(self, request):
        from app.engine.disambiguation import UserChoice
        return UserChoice("candidate", 1)

    def notify(self, message):
        pass


def test_intervencoes_do_usuario_sao_contadas(page):
    page.set_content("""<html><body>
      <div><h3>Caneca azul</h3><button onclick="window.c='azul'">Adicionar</button></div>
      <div><h3>Caneca verde</h3><button onclick="window.c='verde'">Adicionar</button></div>
    </body></html>""")
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, disambiguator=ChooseSecond())
    result = Agent(page, ScriptedPlanner([("click", "Adicionar", None)], []), executor, report=None).run("x")
    assert result.ok and result.interventions == 1
