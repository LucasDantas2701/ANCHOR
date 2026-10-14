"""Sending, saving, paying or exporting only when the request asks for it."""

from pathlib import Path

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.sensitive import classify, unrequested
from anchor.planner import Plan, Step

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_the_rule():
    files = "anexe o currículo eval/fixtures/files/curriculo.pdf e a foto eval/fixtures/files/foto.png"
    assert unrequested(classify("click", "Enviar candidatura"), files, "Enviar candidatura")
    assert unrequested(classify("click", "Exportar planilha"), "Selecione a Ana na lista", "Exportar planilha")
    assert not unrequested(classify("click", "Enviar candidatura"), "anexe o currículo e envie a candidatura", "Enviar candidatura")
    assert not unrequested(classify("click", "Submit application"), "send the application", "Submit application")
    assert not unrequested(classify("click", "Reservar sala"), "reserva a sala Negro amanhã", "Reservar sala")
    assert not unrequested(classify("click", "Salvar cadastro"), "cadastre a Maria no TI", "Salvar cadastro")
    assert not unrequested(classify("click", "Add to cart"), "anything", "Add to cart")          # not sensitive


def test_the_agent_does_not_send_a_form_it_was_only_asked_to_fill(page):
    page.goto((FIXTURES / "application.html").as_uri())
    page.add_init_script("")
    planner = OnePlan(("upload", "Anexar currículo", "eval/fixtures/files/curriculo.pdf"), ("click", "Enviar candidatura", None))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("anexe o currículo eval/fixtures/files/curriculo.pdf")
    assert [r.status for r in result.records] == ["success", "blocked"]


def test_the_agent_sends_it_when_asked(page):
    page.goto((FIXTURES / "application.html").as_uri())
    planner = OnePlan(("upload", "Anexar currículo", "eval/fixtures/files/curriculo.pdf"), ("click", "Enviar candidatura", None))
    result = Agent(page, planner, ActionExecutor(page), report=None).run(
        "anexe o currículo eval/fixtures/files/curriculo.pdf e envie a candidatura")
    assert [r.status for r in result.records] == ["success", "success"]


def test_printing_is_blocked_unless_the_request_asks_for_it(page):
    from anchor.engine.sensitive import unrequested_print
    assert unrequested_print("exporte a tabela de vendas por região", "Imprimir relatório")
    assert not unrequested_print("imprima o relatório", "Imprimir relatório")
    assert not unrequested_print("print the report", "Print report")
    assert not unrequested_print("exporte a tabela", "Vendas por região")

    page.goto((FIXTURES / "report.html").as_uri())
    planner = OnePlan(("click", "Imprimir relatório", None), ("extract_table", "Vendas por região", None))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("exporte a tabela de vendas por região")
    assert result.records[0].status == "blocked"
