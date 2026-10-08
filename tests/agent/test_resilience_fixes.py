"""Fixes found with the resilience benchmark's diagnosis run (development set)."""

from anchor.agent import Agent
from anchor.automations.runner import _unredone_steps
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step

USERS = """<html><body><button onclick="document.body.dataset.all=1">Excluir tudo</button>
  <table><tr><td>Bruno Lima</td><td><button onclick="document.body.dataset.bruno=1">Excluir</button></td></tr>
  <tr><td>Carla Mendes</td><td><button>Excluir</button></td></tr></table></body></html>"""


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def run(page, html, request, *steps):
    page.set_content(html)
    page.set_default_timeout(1500)
    return Agent(page, OnePlan(*steps), ActionExecutor(page), report=None).run(request)


# 1. The destructive barrier looks at what the step is about ------------------------

def test_deleting_everything_is_blocked_when_the_request_names_one_user(page):
    result = run(page, USERS, "Exclua o usuário Bruno Lima", ("click", "Excluir tudo", None))
    assert result.records[0].status == "blocked" and page.evaluate("document.body.dataset.all") is None


def test_deleting_what_the_request_names_is_allowed(page):
    run(page, USERS, "Exclua o usuário Bruno Lima", ("click", "Excluir (Bruno Lima)", None))
    assert page.evaluate("document.body.dataset.bruno") == "1"


def test_deleting_everything_is_allowed_when_the_request_says_so(page):
    run(page, USERS, "Exclua todos os usuários", ("click", "Excluir tudo", None))
    assert page.evaluate("document.body.dataset.all") == "1"


# 2. A lookalike with an extra word loses to the element with the requested name ------

def test_the_element_whose_name_the_request_covers_wins_over_a_lookalike(page):
    page.set_content("""<html><body><button class="real">Salvar cadastro</button>
        <button class="decoy">Salvar cadastro depois</button></body></html>""")
    result = ActionExecutor(page).hover("Salvar cadastro")
    assert result.status == "success" and result.selected_element.text == "Salvar cadastro"


# 3. The contract of a healed plan is one to one, on the same thing ------------------

class R:
    def __init__(self, action, description, value=None, element=""):
        self.step, self.status, self.element = Step(action, description, value), "success", element


def test_accepting_cookies_does_not_redo_opening_the_cart():
    saved = [Step("click", "Add to cart of Ceramic mug", None), Step("click", "shopping cart link", None)]
    done = [R("click", "Accept cookies"), R("click", "Add to cart of Ceramic mug", element="Add to cart")]
    assert _unredone_steps(saved, 0, done) == ["click shopping cart link"]


def test_adding_the_laptop_does_not_redo_adding_the_headphones():
    saved = [Step("click", "Add to cart of UltraBook 14", None), Step("click", "Add to cart of QuietMax Headphones", None)]
    done = [R("click", "shopping cart 2"), R("click", "Add to cart do UltraBook 14")]
    assert _unredone_steps(saved, 0, done) == ["click Add to cart of QuietMax Headphones"]


def test_a_renamed_field_filled_with_the_same_value_redoes_the_step():
    saved = [Step("fill", "Nome", "Bruno Reis")]
    assert _unredone_steps(saved, 0, [R("fill", "Funcionário", "Bruno Reis")]) == []


# 4. A step that undoes an earlier one is noticed --------------------------------------

def test_checking_another_radio_undoes_the_earlier_choice(page):
    html = """<html><body><label><input type="radio" name="t" value="clt"> CLT</label>
        <label><input type="radio" name="t" value="pj"> PJ</label></body></html>"""
    result = run(page, html, "cadastre como PJ", ("check", "PJ", None), ("check", "CLT", None))
    assert result.records[0].status == "success"
    assert result.records[1].status != "success" and "PJ" in result.records[1].note
