"""
Planner prompt language: Portuguese by default (the measured one), English as an
option. With English, everything the model reads must be in English.
"""

import json

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.planner import LLMPlanner, page_elements
from anchor.planner.prompt import SYSTEM, SYSTEM_EN
from tests.planner.test_planner import FakeClient

FORM = """<html><body><label for="n">Nome</label><input id="n">
  <select aria-label="Departamento"><option>TI</option><option>RH</option></select>
  <button onclick="document.body.dataset.s=1">Salvar</button></body></html>"""


def plan_json(*steps, goals=None):
    return json.dumps({"goals": goals or [], "steps": [dict(action=a, description=d, value=v, goal=g, expect=None)
                                                          for a, d, v, g in steps]})


def test_portuguese_is_the_default():
    client = FakeClient(plan_json())
    LLMPlanner(client, "falso").plan("salve", "http://x")
    assert client.calls[0]["messages"][0]["content"] == SYSTEM
    assert client.calls[0]["messages"][1]["content"].startswith("Página aberta: http://x")


def test_english_prompt_and_user_message():
    client = FakeClient(plan_json())
    LLMPlanner(client, "falso", language="en").plan("save it", "http://x", ['Button "Save"'])
    system, user = (m["content"] for m in client.calls[0]["messages"])
    assert system == SYSTEM_EN
    assert user.startswith("Open page: http://x\n\nUser request: save it")
    assert "Visible elements on the page:" in user


def test_english_plan_errors_go_back_in_english():
    bad = plan_json(("fill", "Nome", None, None))
    good = plan_json(("fill", "Nome", "Ana", None))
    client = FakeClient(bad, good)
    LLMPlanner(client, "falso", language="en").plan("fill in Ana", "http://x")
    assert 'the "fill" action needs a value' in client.calls[1]["messages"][-1]["content"]
    assert client.calls[1]["messages"][-1]["content"].startswith("Invalid plan:")


def test_page_summary_follows_the_prompt_language(page):
    page.set_content(FORM)
    pt = page_elements(ElementResolver(page))
    en = page_elements(ElementResolver(page), language="en")
    assert 'Lista de opções "Departamento" [opções: TI | RH]' in pt
    assert 'Dropdown "Departamento" [options: TI | RH]' in en


def test_agent_history_follows_the_prompt_language(page):
    page.set_content(FORM)
    page.set_default_timeout(1500)
    client = FakeClient(plan_json(("fill", "Nome", "Ana", None), ("click", "Botão que não existe", None, None)),
                        plan_json(("click", "Salvar", None, None)),
                        plan_json())
    result = Agent(page, LLMPlanner(client, "falso", language="en"), ActionExecutor(page),
                   report=None, verify_effect=False).run("register Ana")
    assert result.ok
    replan = client.calls[1]["messages"][1]["content"]
    assert "What has already happened in this run:" in replan
    assert '- done: fill Nome = "Ana"' in replan
    assert "- failed: click Botão que não existe — no element on the page matches this description" in replan


def test_unknown_prompt_language_is_rejected():
    with pytest.raises(ValueError):
        LLMPlanner(FakeClient(), "falso", language="fr")
