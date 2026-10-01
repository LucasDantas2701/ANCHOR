"""
Tests of the agent loop, with a scripted planner (ready-made plans, in
sequence) and real test pages.
"""

from pathlib import Path

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, PlanError, Step


class ScriptedPlanner:
    """Returns the plans in the list, one per call, and keeps what it received."""

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
    # Effect verification has its own tests (test_effects.py); here the pages
    # only change internal variables, with no visible effect.
    kwargs.setdefault("verify_effect", False)
    page.set_default_timeout(1500)
    return Agent(page, planner, ActionExecutor(page), report=None, **kwargs).run("faça a tarefa da página")


def test_runs_the_plan_and_checks_the_end(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria"), ("fill", "E-mail", "maria@x.com"), ("click", "Salvar", None)],
        [],  # end check: nothing is left
    )
    result = run(page, planner)

    assert result.ok and result.message == "goal reached"
    assert page.input_value("#nome") == "Maria" and page.evaluate("window.salvo") is True
    assert result.llm_calls == 2 and result.replans == 0 and result.failures == 0
    assert result.tokens_in == 200 and result.tokens_out == 40
    assert "feito: click Salvar" in planner.calls[1]["history"][-1]


def test_end_check_completes_what_was_missing(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria")],
        [("click", "Salvar", None)],   # the check found a missing step
        [],
    )
    result = run(page, planner)
    assert result.ok and page.evaluate("window.salvo") is True
    assert result.llm_calls == 3 and result.replans == 1


def test_without_end_check(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([("fill", "Nome", "Maria")]), verify_end=False)
    assert result.ok and result.llm_calls == 1


def test_navigation_triggers_replanning_with_the_new_page(page, tmp_path: Path):
    (tmp_path / "passo2.html").write_text(
        '<html><body><label for="cpf">CPF</label><input id="cpf">'
        '<button onclick="window.enviado=true">Enviar</button></body></html>', encoding="utf-8")
    (tmp_path / "passo1.html").write_text(
        '<html><body><label for="nome">Nome</label><input id="nome">'
        '<a href="passo2.html">Próximo</a></body></html>', encoding="utf-8")
    page.goto((tmp_path / "passo1.html").as_uri())

    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria"), ("click", "Próximo", None), ("fill", "passo que não existe mais", "x")],
        [("fill", "CPF", "123"), ("click", "Enviar", None)],   # replanned on the new page
        [],
    )
    result = run(page, planner)

    assert result.ok
    assert page.url.endswith("passo2.html") and page.input_value("#cpf") == "123"
    replan = planner.calls[1]
    assert replan["url"].endswith("passo2.html")
    assert any("CPF" in e for e in replan["elements"])            # received the new page's elements
    assert replan["history"] == ["feito: fill Nome = \"Maria\"", "feito: click Próximo"]
    assert result.replans == 1


def test_failure_triggers_replanning_with_the_reason(page):
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


def test_three_failures_cancel_and_report(page):
    page.set_content(FORM)
    bad = [("click", "Botão que não existe", None)]
    result = run(page, ScriptedPlanner(bad, bad, bad))

    assert result.status == "cancelled" and result.failures == 3
    assert "3 failed attempts" in result.message
    assert "Botão que não existe" in result.message


def test_modal_covering_the_button_is_closed_when_replanning(page):
    page.set_content("""<html><body>
      <button id="salvar" onclick="window.salvo=true">Salvar</button>
      <div id="modal" style="position:fixed;inset:0;background:#fff">
        <p>Aceite os cookies</p>
        <button onclick="document.getElementById('modal').remove()">Fechar aviso</button>
      </div></body></html>""")
    planner = ScriptedPlanner(
        [("click", "Salvar", None)],
        [("click", "Fechar aviso", None)],
        [("click", "Salvar", None)],   # replanned because the pop-up closed
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.salvo") is True
    assert "coberto por outro" in planner.calls[1]["history"][0]



def test_empty_initial_plan_cancels(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([]))
    assert result.status == "cancelled" and "cannot be done" in result.message


def test_replanning_with_no_way_out_cancels(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner([("click", "Botão que não existe", None)], []))
    assert result.status == "cancelled" and "found no other way" in result.message


def test_model_error_ends_with_a_message(page):
    page.set_content(FORM)
    result = run(page, ScriptedPlanner(PlanError("resposta inválida")))
    assert result.status == "failed" and "resposta inválida" in result.message


def test_step_limit(page):
    page.set_content(FORM)
    loop = [("fill", "Nome", f"Maria {i}") for i in range(10)]
    result = run(page, ScriptedPlanner(loop), max_steps=4)
    assert result.status == "failed" and "limit of 4 steps" in result.message


class ChooseSecond:
    def choose(self, request):
        from anchor.engine.disambiguation import UserChoice
        return UserChoice("candidate", 1)

    def notify(self, message):
        pass


def test_user_interventions_are_counted(page):
    page.set_content("""<html><body>
      <div><h3>Caneca azul</h3><button onclick="window.c='azul'">Adicionar</button></div>
      <div><h3>Caneca verde</h3><button onclick="window.c='verde'">Adicionar</button></div>
    </body></html>""")
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, disambiguator=ChooseSecond())
    result = Agent(page, ScriptedPlanner([("click", "Adicionar", None)], []), executor, report=None, verify_effect=False).run("x")
    assert result.ok and result.interventions == 1



# --------------------------------------------------------------------------
# Real cases that became tests (version 0.2.1)
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


def test_opening_popup_triggers_replanning_with_its_elements(page):
    page.set_content(SEARCH_POPUP)
    planner = ScriptedPlanner(
        [("click", "Search /", None), ("fill", "campo que o modelo imaginou", "pi network")],
        [("fill", "Buscar moedas", "pi network"), ("press", "Buscar moedas", "Enter")],
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.buscou") == "pi network"
    replan = planner.calls[1]
    assert replan["elements"][0].startswith('Campo de texto "Buscar moedas"')   # the pop-up comes first...
    assert "[pop-up]" in replan["elements"][0]                                 # ...marked
    assert not any("Menu 5" in e for e in replan["elements"])                   # what was covered is left out


def test_summary_shows_the_popup_even_on_a_large_page(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    page.set_content(SEARCH_POPUP.replace(" hidden role", " role"))  # pop-up already open
    lines = page_elements(ElementResolver(page), limit=80)
    assert any("Buscar moedas" in line for line in lines)


ENTER_ONLY = """<html><body>
  <label for="s">Pesquisar</label>
  <input id="s" onkeydown="if(event.key==='Enter') window.buscou=this.value">
</body></html>"""


def test_search_without_button_uses_enter_in_the_field(page):
    page.set_content(ENTER_ONLY)
    planner = ScriptedPlanner([("fill", "Pesquisar", "rpa em manaus"), ("click", "Pesquisar", None)], [])
    result = run(page, planner)

    assert result.ok and page.evaluate("window.buscou") == "rpa em manaus"
    assert result.records[1].resolved_by == "enter_in_field"
    assert result.interventions == 0


def test_fill_never_picks_a_button(page):
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


def test_step_repeated_after_replanning_is_blocked(page):
    page.set_content(JOBS)
    planner = ScriptedPlanner(
        [("click", "Consultor RPA", None)],
        [("click", "Consultor RPA", None)],     # the URL changed; the model repeats the click
        [("click", "Salvar vaga", None)],       # once warned, it moves on
        [],
    )
    result = run(page, planner)

    assert result.ok and page.evaluate("window.salva") is True
    assert page.evaluate("window.fechada") is None
    assert result.failures == 1 and result.records[1].status == "loop"
    assert "não o repita" in planner.calls[2]["history"][-1]


def test_end_check_has_a_limit(page):
    page.set_content(FORM)
    planner = ScriptedPlanner(
        [("fill", "Nome", "Maria")],
        [("fill", "E-mail", "a@x.com")],        # 1st check: finds something
        [("click", "Salvar", None)],            # 2nd check: finds more
    )
    result = run(page, planner)
    assert result.status == "cancelled" and "end check" in result.message
    assert page.evaluate("window.salvo") is True


def test_request_without_verb_does_not_pick_the_destructive_action(page):
    page.set_content("""<html><body><ul>
      <li><a href="#v1" onclick="window.aberta=true">Consultor RPA</a>
          <button aria-label="Fechar vaga de Consultor RPA" onclick="window.fechada=true">✕</button></li>
    </ul></body></html>""")
    # The link changes the URL (#v1): replanning (nothing left) and the end check.
    result = run(page, ScriptedPlanner([("click", "Consultor RPA", None)], [], []))
    assert result.ok and page.evaluate("window.aberta") is True
    assert page.evaluate("window.fechada") is None


def test_end_check_repeating_only_done_steps_counts_as_the_end(page):
    page.set_content(FORM)
    planner = ScriptedPlanner([("click", "Salvar", None)], [("click", "Salvar", None)])
    result = run(page, planner)
    assert result.ok and result.message == "goal reached" and result.failures == 0


def test_unrequested_destructive_action_is_blocked(page):
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


def test_requested_destructive_action_is_not_blocked(page):
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


def test_suggestions_while_typing_do_not_trigger_replanning(page):
    page.set_content(SUGGESTIONS)
    planner = ScriptedPlanner([("fill", "Pesquisar", "rpa em manaus"), ("click", "Opção rpa em manaus", None)], [])
    result = run(page, planner)
    assert result.ok and result.replans == 0
    assert page.evaluate("window.escolhida") == "rpa em manaus"   # the exact suggestion, not the "júnior" one
