"""When the person says it is none of the elements found: the planner hears why; a login comes first: wait, then replan."""
from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation.types import UserChoice
from anchor.planner import Plan, Step

PORTAL = """<html><body><h1>PORTAL DO ALUNO</h1><button>ACESSAR</button><a href="#">Esqueceu sua senha?</a>
  <select aria-label="Alias"><option>a</option></select></body></html>"""
INSIDE = """<html><body><h1>Início</h1><a href="#" onclick="document.body.insertAdjacentHTML('beforeend','<p>Relatório 2026</p>')">Relatórios</a></body></html>"""


class Planner:
    """Gives the plans in order, and keeps the history it was given each time."""

    def __init__(self, *plans):
        self.plans, self.histories = list(plans), []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.histories.append(list(history or []))
        steps = self.plans.pop(0) if self.plans else []
        return Plan(steps=[Step(*s) for s in steps])


class Person:
    def __init__(self, choice):
        self.choice, self.asked = choice, 0

    def choose(self, request):
        self.asked += 1
        return self.choice

    def notify(self, message):
        pass


def test_none_of_these_with_a_reason_reaches_the_planner(page):
    page.set_content(PORTAL)
    planner = Planner([("click", "relatorios")])
    person = Person(UserChoice("none", note="the reports are inside the portal: you have to log in first"))
    Agent(page, planner, ActionExecutor(page, disambiguator=person), report=None).run("abra os relatorios")
    assert person.asked == 1 and len(planner.histories) >= 2
    told = " ".join(planner.histories[1])
    assert "nenhum dos elementos encontrados" in told and "you have to log in first" in told


def test_a_login_comes_first_waits_for_it_and_plans_again(page):
    page.set_content(PORTAL)

    class Waiter:
        calls = 0

        def wait(self, url, signup=False):
            Waiter.calls += 1
            page.set_content(INSIDE)                 # the person logged in
            return True

    planner = Planner([("click", "relatorios")], [("click", "Relatórios")])
    person = Person(UserChoice("login"))
    result = Agent(page, planner, ActionExecutor(page, disambiguator=person), report=None,
                   login=Waiter()).run("abra os relatorios")
    assert Waiter.calls == 1 and result.ok
    assert any(r.status == "login" for r in result.records)
