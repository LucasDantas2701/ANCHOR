"""
Testes do loop do agente, com um planejador roteirizado (planos prontos,
em sequência) e páginas de teste reais.
"""

from pathlib import Path

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, PlanError, Step


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
    # A verificação do efeito tem testes próprios (test_effects.py); aqui as páginas
    # só mudam variáveis internas, sem efeito visível.
    kwargs.setdefault("verify_effect", False)
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
        [("click", "Fechar aviso", None)],
        [("click", "Salvar", None)],   # replanejado porque o pop-up fechou
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
    loop = [("fill", "Nome", f"Maria {i}") for i in range(10)]
    result = run(page, ScriptedPlanner(loop), max_steps=4)
    assert result.status == "failed" and "limite de 4 passos" in result.message


class ChooseSecond:
    def choose(self, request):
        from anchor.engine.disambiguation import UserChoice
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
    result = Agent(page, ScriptedPlanner([("click", "Adicionar", None)], []), executor, report=None, verify_effect=False).run("x")
    assert result.ok and result.interventions == 1



# --------------------------------------------------------------------------
# Casos reais que viraram testes (versão 0.2.1)
# --------------------------------------------------------------------------

SEARCH_POPUP = """<html><body>
  <header>""" + "".join(f'<a href="#l{i}">Menu {i}</a>' for i in range(90)) + """
    <div class="lupa" style="cursor:pointer;display:inline-block" onclick="document.getElementById('busca').hidden=false">Search /</div>
  </header>
  <div id="busca" hidden role="dialog" style="position:fixed;inset:0;background:#fff">
    <label for="q">Buscar moedas</label><input id="q"
      onkeydown="if(event.key==='Enter') window.buscou=this.value">
  </div>
</body></html>"""


def test_popup_que_abre_gera_replanejamento_com_os_elementos_dele(page):
    page.set_content(SEARCH_POPUP)
    planner = ScriptedPlanner(
        [("click", "Search /", None), ("fill", "campo que o modelo imaginou", "pi network")],
        [("fill", "Buscar moedas", "pi network"), ("press", "Buscar moedas", "Enter")],
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.buscou") == "pi network"
    replan = planner.calls[1]
    assert replan["elements"][0].startswith('Campo de texto "Buscar moedas"')   # o pop-up vem primeiro...
    assert "[pop-up]" in replan["elements"][0]                                 # ...marcado
    assert not any("Menu 5" in e for e in replan["elements"])                   # o que ficou coberto sai


def test_resumo_mostra_o_popup_mesmo_numa_pagina_grande(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    page.set_content(SEARCH_POPUP.replace(" hidden role", " role"))  # pop-up já aberto
    lines = page_elements(ElementResolver(page), limit=80)
    assert any("Buscar moedas" in line for line in lines)


ENTER_ONLY = """<html><body>
  <label for="s">Pesquisar</label>
  <input id="s" onkeydown="if(event.key==='Enter') window.buscou=this.value">
</body></html>"""


def test_busca_sem_botao_usa_enter_no_campo(page):
    page.set_content(ENTER_ONLY)
    planner = ScriptedPlanner([("fill", "Pesquisar", "rpa em manaus"), ("click", "Pesquisar", None)], [])
    result = run(page, planner)

    assert result.ok and page.evaluate("window.buscou") == "rpa em manaus"
    assert result.records[1].resolved_by == "enter_no_campo"
    assert result.interventions == 0


def test_preencher_nunca_escolhe_um_botao(page):
    page.set_content("""<html><body>
      <button>Filtros, Título da vaga</button>
      <label for="t">Título</label><input id="t">
    </body></html>""")
    result = run(page, ScriptedPlanner([("fill", "Filtros, Título da vaga", "RPA")], []))
    assert result.ok and page.input_value("#t") == "RPA"


JOBS = """<html><body>
  <ul>
    <li><a href="#vaga1" onclick="document.getElementById('det').hidden=false">Consultor RPA</a>
        <button onclick="window.fechada=true">Ocultar</button></li>
    <li><a href="#vaga2">Desenvolvedor RPA</a></li>
  </ul>
  <section id="det" hidden><h2>Consultor RPA</h2>
    <button onclick="window.salva=true">Salvar vaga</button></section>
</body></html>"""


def test_passo_repetido_depois_de_replanejar_e_barrado(page):
    page.set_content(JOBS)
    planner = ScriptedPlanner(
        [("click", "Consultor RPA", None)],
        [("click", "Consultor RPA", None)],     # a URL mudou; o modelo repete o clique
        [("click", "Salvar vaga", None)],       # avisado, ele segue em frente
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.salva") is True
    assert page.evaluate("window.fechada") is None
    assert result.failures == 1 and result.records[1].status == "loop"
    assert "não o repita" in planner.calls[2]["history"][-1]


def test_conferencia_do_fim_tem_limite(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria")],
        [("fill", "E-mail", "a@x.com")],        # 1ª conferência: acha algo
        [("click", "Salvar", None)],            # 2ª conferência: acha mais
    )
    result = run(page, planner)
    assert result.status == "cancelled" and "conferência do fim" in result.message
    assert page.evaluate("window.salvo") is True


def test_pedido_sem_verbo_nao_escolhe_a_acao_destrutiva(page):
    page.set_content("""<html><body><ul>
      <li><a href="#v1" onclick="window.aberta=true">Consultor RPA</a>
          <button aria-label="Fechar vaga de Consultor RPA" onclick="window.fechada=true">✕</button></li>
    </ul></body></html>""")
    # O link muda a URL (#v1): replanejamento (nada falta) e conferência do fim.
    result = run(page, ScriptedPlanner([("click", "Consultor RPA", None)], [], []))
    assert result.ok and page.evaluate("window.aberta") is True
    assert page.evaluate("window.fechada") is None


def test_conferencia_que_so_repete_passos_feitos_conta_como_fim(page):
    page.set_content(FORM)
    planner = ScriptedPlanner([("click", "Salvar", None)], [("click", "Salvar", None)])
    result = run(page, planner)
    assert result.ok and result.message == "objetivo atingido" and result.failures == 0


def test_acao_destrutiva_nao_pedida_e_barrada(page):
    page.set_content("""<html><body><ul>
      <li><a href="#" onclick="document.getElementById('d').hidden=false;return false">Consultor RPA</a>
          <button onclick="window.fechada=true">Fechar vaga de Consultor RPA</button></li></ul>
      <section id="d" hidden><button onclick="window.salva=true">Salvar vaga</button></section>
    </body></html>""")
    planner = ScriptedPlanner(
        [("click", "Consultor RPA", None), ("click", "Fechar vaga de Consultor RPA", None), ("click", "Salvar vaga", None)],
        [],
    )
    result = Agent(page, planner, ActionExecutor(page), report=None, verify_effect=False).run("salve a primeira vaga")
    assert result.ok and page.evaluate("window.salva") is True
    assert page.evaluate("window.fechada") is None
    assert [r.status for r in result.records] == ["success", "blocked", "success"]


def test_acao_destrutiva_pedida_nao_e_barrada(page):
    page.set_content('<html><body><button onclick="window.fechada=true">Fechar vaga de Consultor RPA</button></body></html>')
    planner = ScriptedPlanner([("click", "Fechar vaga de Consultor RPA", None)], [])
    result = Agent(page, planner, ActionExecutor(page), report=None, verify_effect=False).run("feche a vaga de consultor rpa")
    assert result.ok and page.evaluate("window.fechada") is True


SUGGESTIONS = """<html><body>
  <input id="s" aria-label="Pesquisar"
    oninput="const l=document.getElementById('sug'); l.hidden=!this.value;
             l.innerHTML=['', ' júnior'].map(x=>`<div role=option style='cursor:pointer'
               onclick='window.escolhida=this.textContent'>${this.value}${x}</div>`).join('')">
  <div id="sug" role="listbox" hidden></div>
</body></html>"""


def test_sugestoes_ao_digitar_nao_geram_replanejamento(page):
    page.set_content(SUGGESTIONS)
    planner = ScriptedPlanner([("fill", "Pesquisar", "rpa em manaus"), ("click", "Opção rpa em manaus", None)], [])
    result = run(page, planner)
    assert result.ok and result.replans == 0
    assert page.evaluate("window.escolhida") == "rpa em manaus"   # a sugestão exata, não a "júnior"
