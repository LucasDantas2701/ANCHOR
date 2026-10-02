"""Sensitive actions: asked after the element is found and before the action; a denial stops."""

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.sensitive import AllowAll, TerminalConfirmer, classify
from anchor.planner import Plan, Step

PAGE = """<html><body>
  <div><span>Bruno Lima</span> <button onclick="document.body.dataset.deleted=1">Excluir</button></div>
  <button onclick="document.body.dataset.added=1">Adicionar ao carrinho</button></body></html>"""


@pytest.mark.parametrize("action, description, element, expected", [
    ("click", "Excluir (Bruno Lima)", "Excluir", "delete"),
    ("click", "clicar no botão", "Delete", "delete"),          # vague step, sensitive element
    ("click", "Salvar cadastro", "", "submit"),
    ("click", "Pagar com cartão", "", "pay"),
    ("click", "Exportar planilha", "", "download"),
    ("click", "Easy apply", "", "send"),
    ("click", "Add to cart (UltraBook)", "Add to cart", None),
    ("click", "Search", "", None),
    ("fill", "Salvar", "", None),                              # only clicks are sensitive
    ("click", "Cancel order (Order #1024 View details)", "Cancel order", None),   # context in ()
])
def test_classify(action, description, element, expected):
    assert classify(action, description, element) == expected


class Recorder:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def confirm(self, request):
        self.asked.append(request)
        return self.answer


def test_denied_action_is_not_performed(page):
    page.set_content(PAGE)
    confirmer = Recorder(False)
    result = ActionExecutor(page, confirmer=confirmer).click("Excluir")
    assert result.status == "denied" and page.evaluate("document.body.dataset.deleted") is None
    assert confirmer.asked[0].category == "delete" and confirmer.asked[0].element == "Excluir"


def test_allowed_action_is_performed(page):
    page.set_content(PAGE)
    assert ActionExecutor(page, confirmer=Recorder(True)).click("Excluir").status == "success"
    assert page.evaluate("document.body.dataset.deleted") == "1"


def test_ordinary_actions_and_runs_without_a_confirmer_ask_nothing(page):
    page.set_content(PAGE)
    confirmer = Recorder(False)
    assert ActionExecutor(page, confirmer=confirmer).click("Adicionar ao carrinho").status == "success"
    assert confirmer.asked == []
    assert ActionExecutor(page).click("Excluir").status == "success"     # evaluations, tests


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_a_denial_stops_the_agent_without_replanning(page):
    page.set_content(PAGE)
    planner = OnePlan(("click", "Excluir", None))
    result = Agent(page, planner, ActionExecutor(page, confirmer=Recorder(False)), report=None,
                   verify_effect=False).run("exclua o Bruno Lima")
    assert result.status == "cancelled" and result.denied and planner.calls == 1
    assert result.message.startswith("stopped: you did not allow")


def test_terminal_confirmer():
    assert TerminalConfirmer(input_fn=lambda _: "s", output=lambda _: None, interactive=True).confirm(_req())
    assert TerminalConfirmer(input_fn=lambda _: "yes", output=lambda _: None, interactive=True).confirm(_req())
    assert not TerminalConfirmer(input_fn=lambda _: "", output=lambda _: None, interactive=True).confirm(_req())
    # With no one to answer, the answer is no.
    assert not TerminalConfirmer(input_fn=lambda _: "s", output=lambda _: None, interactive=False).confirm(_req())
    assert AllowAll().confirm(_req())


def _req():
    from anchor.engine.sensitive import ConfirmationRequest
    return ConfirmationRequest("click", "Excluir", "Excluir", "delete")
