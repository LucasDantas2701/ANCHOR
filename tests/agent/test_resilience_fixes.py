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


def test_undoing_an_unrequested_choice_with_the_requested_one_is_a_correction(page):
    html = """<html><body><label><input type="radio" name="t" value="e"> Employee</label>
        <label><input type="radio" name="t" value="c"> Contractor</label></body></html>"""
    result = run(page, html, "register Maria as a contractor", ("check", "Employee", None), ("check", "Contractor", None))
    assert [r.status for r in result.records] == ["success", "success"]


def test_the_tie_break_only_acts_between_a_name_and_its_lookalike(page, monkeypatch):
    """SauceDemo: "Open Menu" and the cart are not a name and its lookalike: nothing changes."""
    from anchor.engine.element_resolver import ElementResolver, constants
    page.set_content("""<html><body><button>Open Menu</button>
        <a href="#" aria-label="Cart, empty" style="display:inline-block;width:24px;height:24px"></a>
        <button>Salvar cadastro</button><button>Salvar cadastro depois</button></body></html>""")

    def scores(query):
        return {(m.text or m.label): round(m.score, 4) for m in ElementResolver(page).query(query, k=5, action="click")}

    with_tie_break = scores("abrir o carrinho"), scores("Salvar cadastro")
    monkeypatch.setattr(constants, "NAME_COVERED_BONUS", 0.0)
    without = scores("abrir o carrinho"), scores("Salvar cadastro")
    assert with_tie_break[0] == without[0]                                        # no lookalike: unchanged
    assert with_tie_break[1]["Salvar cadastro"] > without[1]["Salvar cadastro"]   # the name asked wins
    assert with_tie_break[1]["Salvar cadastro depois"] == without[1]["Salvar cadastro depois"]


def test_when_both_choices_are_in_the_request_the_later_one_stands(page):
    """en-reg-01: "Register the employee Maria ... contractor", with Employee and Contractor options."""
    html = """<html><body><label><input type="radio" name="t" value="e"> Employee</label>
        <label><input type="radio" name="t" value="c"> Contractor</label></body></html>"""
    result = run(page, html, "Register the employee Maria Silva, contractor",
                 ("check", "Employee", None), ("click", "Contractor", None))
    assert [r.status for r in result.records] == ["success", "success"]
