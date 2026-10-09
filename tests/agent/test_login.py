"""Logging in by hand: ANCHOR never types a password, and waits for the user when a task needs a login."""

import pytest

from anchor.agent import Agent
from anchor.agent.login import (
    TerminalLoginWaiter,
    password_field,
    request_has_password,
    wants_login,
)
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step

LOGIN = """<html><body><h1>Entrar</h1>
  <label>E-mail <input id="email"></label>
  <label>Senha <input id="senha" type="password"></label>
  <button>Entrar</button></body></html>"""
AFTER = """<html><body><h1>Início</h1><input aria-label="Pesquisar vagas">
  <button onclick="document.body.insertAdjacentHTML('beforeend', '<p>12 vagas</p>')">Pesquisar</button></body></html>"""


@pytest.mark.parametrize("request_, has", [
    ("faça o login com o email ana@x.com e senha 27012005 e pesquise vagas", True),
    ("preencha email ana@x.com e senha: hunter", True),
    ("log in with password hunter2", True),
    ('entre com a senha "minha senha"', True),
    ("troque a senha do wifi", False),
    ("redefina a senha e salve", False),
    ("esqueci minha senha", False),
    ("pesquise vagas de rpa em manaus", False),
])
def test_a_password_in_the_request_is_recognized(request_, has):
    assert request_has_password(request_) is has


def test_a_request_to_log_in_is_recognized():
    assert wants_login("faça login e pesquise vagas") and wants_login("Sign in and open my orders")
    assert not wants_login("troque o idioma da página para português")


def test_the_executor_refuses_to_type_into_a_password_field(page):
    page.set_content(LOGIN)
    executor = ActionExecutor(page)
    executor.refuse_passwords = True
    result = executor.fill("Senha", "27012005")
    assert result.status == "credential" and page.input_value("#senha") == ""
    assert executor.fill("E-mail", "ana@x.com").status == "success"          # other fields are fine


class Planner:
    def __init__(self, *plans):
        self.plans, self.calls = list(plans), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        steps = self.plans.pop(0) if self.plans else []
        return Plan(steps=[Step(*s) for s in steps])


class FakeWaiter:
    """Logs in "by hand": replaces the page with the logged-in one."""

    def __init__(self, page, html=AFTER, answer=True):
        self.page, self.html, self.answer, self.calls = page, html, answer, 0

    def wait(self, url):
        self.calls += 1
        if self.answer:
            self.page.set_content(self.html)
        return self.answer


def test_a_password_in_the_request_never_reaches_the_model(page):
    page.set_content(LOGIN)
    planner = Planner([("fill", "E-mail", "ana@x.com")])
    result = Agent(page, planner, ActionExecutor(page), report=None).run("entre com ana@x.com e senha 1234")
    assert not result.ok and planner.calls == 0 and "password" in result.message


def test_nothing_plannable_on_a_login_page_waits_for_the_login_then_goes_on(page):
    page.set_content(LOGIN)
    planner = Planner([], [("click", "Pesquisar", None)])              # 1st: nothing on the login page
    waiter = FakeWaiter(page)
    result = Agent(page, planner, ActionExecutor(page), report=None, login=waiter).run("pesquise vagas")
    assert result.ok and waiter.calls == 1 and result.logins == 1 and planner.calls >= 2


def test_a_planned_password_is_not_typed_the_user_logs_in(page):
    page.set_content(LOGIN)
    planner = Planner([("fill", "E-mail", "ana@x.com"), ("fill", "Senha", "ana@x.com")],
                      [("click", "Pesquisar", None)])
    waiter = FakeWaiter(page)
    result = Agent(page, planner, ActionExecutor(page), report=None, login=waiter).run("entre com ana@x.com e pesquise")
    assert result.ok and result.logins == 1
    assert any(r.status == "credential" for r in result.records)


def test_a_login_the_user_gives_up_stops_the_run(page):
    page.set_content(LOGIN)
    planner = Planner([("fill", "Senha", "x")])
    result = Agent(page, planner, ActionExecutor(page), report=None,
                   login=FakeWaiter(page, answer=False)).run("faça login")
    assert result.status == "cancelled" and "login" in result.message


def test_without_anyone_to_ask_nothing_changes(page):
    """The evaluation runs: a login page with nothing to plan is still 'cannot be done'."""
    page.set_content(LOGIN)
    result = Agent(page, Planner([]), ActionExecutor(page), report=None).run("pesquise vagas")
    assert result.status == "cancelled" and result.logins == 0


def test_a_request_on_a_login_page_that_needs_no_login_is_not_stopped(page):
    """Changing the language of a login page: no password involved, no waiting."""
    page.set_content(LOGIN.replace("<button>Entrar</button>", '<button onclick="document.title=1">Idioma</button>'))
    waiter = FakeWaiter(page)
    result = Agent(page, Planner([("click", "Idioma", None)]), ActionExecutor(page), report=None,
                   login=waiter).run("troque o idioma")
    assert waiter.calls == 0


def test_the_terminal_waiter_cannot_wait_without_a_terminal():
    assert TerminalLoginWaiter(interactive=False).wait("http://x") is False
    said = []
    waiter = TerminalLoginWaiter(input_fn=lambda q: "", output=said.append, interactive=True)
    assert waiter.wait("http://x") is True and "never types passwords" in said[0]
    assert TerminalLoginWaiter(input_fn=lambda q: "q", output=lambda _: None, interactive=True).wait("x") is False


def test_password_field_reports_whether_it_was_filled(page):
    page.set_content(LOGIN)
    assert password_field(page) == {"name": "Senha", "filled": False}
    page.fill("#senha", "x")
    assert password_field(page)["filled"] is True
    page.set_content(AFTER)
    assert password_field(page) is None
