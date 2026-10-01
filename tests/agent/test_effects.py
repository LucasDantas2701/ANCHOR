"""
Effect verification of each action (layer 1) and the field that needs to be revealed.
"""

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import UserChoice
from anchor.engine.memory import ChoiceMemory
from tests.agent.test_agent import ScriptedPlanner


def agent(page, planner, **kwargs):
    page.set_default_timeout(1500)
    executor = kwargs.pop("executor", None) or ActionExecutor(page)
    return Agent(page, planner, executor, report=None, **kwargs)


def test_click_with_visible_effect_passes(page):
    page.set_content("""<html><body>
      <button onclick="document.getElementById('msg').textContent='Cadastro salvo com sucesso'">Salvar</button>
      <p id="msg"></p></body></html>""")
    planner = ScriptedPlanner([("click", "Salvar", None)], [])
    result = agent(page, planner).run("salve")
    assert result.ok and result.no_effect == 0
    assert 'apareceu na página: "Cadastro salvo com sucesso"' in planner.calls[1]["history"]


def test_click_without_effect_is_retried_once_then_fails(page):
    page.set_content("<html><body><button>Salvar</button><button onclick=\"document.body.dataset.ok=1\">Gravar</button></body></html>")
    planner = ScriptedPlanner([("click", "Salvar", None)], [("click", "Gravar", None)], [])
    result = agent(page, planner).run("salve")

    assert result.ok                                    # replanning found another way
    assert result.no_effect == 1 and result.failures == 1
    assert result.records[0].status == "no_effect"
    assert "não teve efeito" in planner.calls[1]["history"][-1]


def test_error_message_turns_the_step_into_a_failure(page):
    page.set_content("""<html><body>
      <label for="cpf">CPF</label><input id="cpf">
      <button onclick="document.getElementById('e').textContent='CPF inválido'">Salvar</button>
      <p id="e" role="alert"></p></body></html>""")
    planner = ScriptedPlanner([("fill", "CPF", "123"), ("click", "Salvar", None)], [])
    result = agent(page, planner).run("salve")

    assert result.status == "cancelled"                 # the planner found no other way
    assert result.records[1].status == "wrong_effect"
    assert 'the message "CPF inválido" appeared' in result.records[1].note


def test_field_that_does_not_keep_the_value_is_detected(page):
    page.set_content("""<html><body><label for="n">Nome</label>
      <input id="n" oninput="this.value=''"></body></html>""")
    planner = ScriptedPlanner([("fill", "Nome", "Maria")], [])
    result = agent(page, planner).run("preencha")
    assert result.records[0].status == "wrong_effect"
    assert 'instead of "Maria"' in result.records[0].note


def test_input_mask_does_not_count_as_an_error(page):
    page.set_content("""<html><body><label for="t">Telefone</label>
      <input id="t" oninput="const d=this.value.replace(/\\D/g,''); this.value=d.length===11 ?
        '('+d.slice(0,2)+') '+d.slice(2,7)+'-'+d.slice(7) : d"></body></html>""")
    planner = ScriptedPlanner([("fill", "Telefone", "92999990000")], [])
    result = agent(page, planner).run("preencha")
    assert result.ok and page.input_value("#t") == "(92) 99999-0000"


def test_remembered_choice_without_effect_is_forgotten(page, tmp_path):
    html = """<html><body>
      <div><h3>Caneca azul</h3><button {a}>Adicionar</button></div>
      <div><h3>Caneca verde</h3><button onclick="document.body.dataset.v=1">Adicionar</button></div></body></html>"""
    memory = ChoiceMemory(tmp_path / "m.json")

    class First:
        def choose(self, request):
            return UserChoice("candidate", next(c.number for c in request.candidates if "azul" in c.near))

        def notify(self, message):
            pass

    page.set_content(html.format(a='onclick="document.body.dataset.a=1"'))
    executor = ActionExecutor(page, disambiguator=First(), memory=memory)
    assert agent(page, ScriptedPlanner([("click", "Adicionar", None)], []), executor=executor).run("x").ok
    assert len(memory.entries) == 1

    page.set_content(html.format(a=""))               # now the blue mug's button does nothing
    executor = ActionExecutor(page, memory=memory)
    result = agent(page, ScriptedPlanner([("click", "Adicionar", None)], []), executor=executor).run("x")
    assert result.records[0].status == "no_effect"
    assert memory.entries == {}


SEARCH = """<html><body>
  <div class="lupa" style="cursor:pointer" onclick="const b=document.getElementById('b'); b.hidden=false; document.getElementById('q').focus()">Search /</div>
  <div id="b" hidden role="dialog"><input id="q" placeholder="Type a coin"
    onkeydown="if(event.key==='Enter') window.buscou=this.value"></div>
</body></html>"""


def test_field_revealed_by_the_magnifier(page):
    page.set_content(SEARCH)
    planner = ScriptedPlanner([("fill", "Search /", "Pi Network"), ("press", "Type a coin", "Enter")], [])
    result = agent(page, planner, verify_effect=False).run("pesquise a moeda Pi Network")

    assert result.ok and page.evaluate("window.buscou") == "Pi Network"
    assert result.records[0].resolved_by == "revealed_field"


def test_enter_without_effect_leads_to_replanning(page):
    page.set_content("""<html><body><label for="s">Buscar</label><input id="s">
      <button onclick="document.body.dataset.b=1">Ir</button></body></html>""")
    planner = ScriptedPlanner(
        [("fill", "Buscar", "rpa"), ("press", "Buscar", "Enter")],
        [("click", "Ir", None)],
        [],
    )
    result = agent(page, planner).run("busque rpa")
    assert result.ok and result.records[1].status == "no_effect"
