"""Iframes: elements, effects, password fields, tables and value texts inside an iframe are seen too."""

from pathlib import Path

from anchor.agent import Agent
from anchor.agent.login import password_field
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.tables import find_tables, value_texts
from anchor.planner import Plan, Step

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def open_newsletter(page, name="newsletter.html"):
    page.goto((FIXTURES / name).as_uri())
    page.wait_for_function("document.getElementById('widget').contentDocument !== undefined")
    page.frames[1].wait_for_selector("#subscribe")


def test_elements_inside_an_iframe_are_indexed_with_their_frame(page):
    open_newsletter(page)
    resolver = ElementResolver(page)
    resolver.index()
    by_id = {r["id"]: r for r in resolver.records}
    assert by_id["el-0"].get("frame") is None                         # the page's own: as before
    framed = [r for r in resolver.records if r.get("frame") == 1]
    assert {r["id"] for r in framed} >= {"f1-el-0", "f1-el-1"}         # numbered apart


def test_the_executor_acts_inside_the_iframe(page):
    open_newsletter(page)
    executor = ActionExecutor(page)
    assert executor.fill("E-mail", "ana@exemplo.com").status == "success"
    assert executor.check("Quero receber ofertas").status == "success"
    assert executor.click("Assinar newsletter").status == "success"
    # The iframe tells the page with postMessage, which arrives a moment later: wait for it.
    page.wait_for_function("window.__frameState.subscribed === 'ana@exemplo.com'", timeout=3000)


def test_a_page_without_iframes_is_indexed_as_before(page):
    page.set_content("<button>Salvar</button><input aria-label='Nome'>")
    resolver = ElementResolver(page)
    resolver.index()
    assert [r["id"] for r in resolver.records] == ["el-0", "el-1"] and all("frame" not in r for r in resolver.records)


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_the_agent_sees_the_effect_of_a_click_inside_the_iframe(page):
    """Without the iframe in the effect check, every click inside one would be 'no visible effect'."""
    open_newsletter(page)
    planner = OnePlan(("fill", "E-mail", "ana@exemplo.com"), ("click", "Assinar newsletter", None))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("assine a newsletter com o e-mail ana@exemplo.com")
    assert result.ok, result.message
    page.wait_for_function("window.__frameState.subscribed === 'ana@exemplo.com'", timeout=3000)


def test_a_login_form_inside_an_iframe_is_recognized(page, tmp_path):
    (tmp_path / "login.html").write_text('<label>Senha <input type="password"></label>')
    (tmp_path / "page.html").write_text('<h1>Banco</h1><iframe src="login.html"></iframe>')
    page.goto((tmp_path / "page.html").as_uri())
    page.frames[1].wait_for_selector("input")
    assert password_field(page) == {"name": "Senha", "filled": False}


def test_tables_and_value_texts_inside_an_iframe_are_read(page, tmp_path):
    (tmp_path / "report.html").write_text(
        "<h2>Vendas</h2><table><tr><th>Região</th></tr><tr><td>Norte</td></tr><tr><td>Sul</td></tr></table><p>Total: 2</p>")
    (tmp_path / "page.html").write_text('<h1>Painel</h1><iframe src="report.html"></iframe>')
    page.goto((tmp_path / "page.html").as_uri())
    page.frames[1].wait_for_selector("table")
    assert [t.name for t in find_tables(page)] == ["Vendas"] and "Total: 2" in value_texts(page)
