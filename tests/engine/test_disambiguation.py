"""
Tests of the user's disambiguation.

A "fake user" (FakeUser) replaces the terminal: it answers
automatically and records what it saw, for the tests to check.
"""

import pytest

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator, UserChoice

PAGE = """
<html><body>
  <script>window.clicks = {a: 0, b: 0, fav: 0};</script>
  <div class="product"><h2>Caneca azul</h2>
    <button id="a" onclick="clicks.a++">Adicionar ao carrinho</button></div>
  <div class="product"><h2>Caneca verde</h2>
    <button id="b" onclick="clicks.b++">Adicionar ao carrinho</button></div>
  <div style="margin-top:40px">
    <span id="fav" onclick="clicks.fav++" style="display:inline-block;width:20px;height:20px;background:#c00"></span>
  </div>
</body></html>
"""


class FakeUser:
    def __init__(self, answer, before_answer=None):
        self.answer = answer
        self.before_answer = before_answer
        self.requests = []
        self.messages = []
        self.badges_seen = None

    def choose(self, request):
        self.requests.append(request)
        if self.before_answer:
            self.before_answer()
        return self.answer

    def notify(self, message):
        self.messages.append(message)


@pytest.fixture
def shop(page):
    page.set_content(PAGE)
    return page


def clicks(page):
    return page.evaluate("window.clicks")


def test_without_disambiguator_keeps_the_old_behavior(shop):
    result = ActionExecutor(shop).click("adicionar ao carrinho")
    assert result.status == "ambiguous"
    assert clicks(shop) == {"a": 0, "b": 0, "fav": 0}


def test_user_picks_the_second_candidate(shop):
    user = FakeUser(UserChoice("candidate", 2))
    result = ActionExecutor(shop, disambiguator=user).click("adicionar ao carrinho")

    assert result.status == "success"
    assert result.resolved_by == "user"
    request = user.requests[0]
    assert request.reason == "ambiguous"
    assert request.screenshot  # with no visible window, an image is sent
    chosen = request.candidates[1]
    assert chosen.kind == "Button"
    assert chosen.name == "Adicionar ao carrinho"
    assert sum(clicks(shop).values()) == 1
    target = "a" if "azul" in chosen.near else "b"
    assert clicks(shop)[target] == 1


def test_numbers_appear_on_the_page_and_disappear_afterwards(shop):
    seen = {}

    def look():
        seen["badges"] = shop.locator(".er-badge").count()
        seen["outlined"] = shop.locator("[data-er-highlight]").count()

    user = FakeUser(UserChoice("candidate", 1), before_answer=look)
    ActionExecutor(shop, disambiguator=user).click("adicionar ao carrinho")

    assert seen["badges"] == len(user.requests[0].candidates) >= 2
    assert seen["outlined"] == seen["badges"]
    assert shop.locator(".er-badge").count() == 0
    assert shop.locator("[data-er-highlight]").count() == 0


def test_user_skips_the_step(shop):
    user = FakeUser(UserChoice("skip"))
    result = ActionExecutor(shop, disambiguator=user).click("adicionar ao carrinho")

    assert result.status == "ambiguous"
    assert result.resolved_by == "user_skipped"
    assert clicks(shop) == {"a": 0, "b": 0, "fav": 0}


def test_user_clicks_the_element_and_the_click_does_not_fire_twice(shop):
    # Simulates the user's click in the browser right after the "C" answer.
    def schedule_user_click():
        shop.evaluate(
            "setTimeout(() => document.getElementById('fav')"
            ".dispatchEvent(new MouseEvent('click', {bubbles: true})), 300)"
        )

    user = FakeUser(UserChoice("point"), before_answer=schedule_user_click)
    executor = ActionExecutor(shop, disambiguator=user, can_point=True, point_timeout_s=5)
    result = executor.click("marcar a caneca como favorita")

    assert user.requests[0].reason == "not_found"
    assert result.status == "success"
    assert result.resolved_by == "user"
    assert user.messages  # told the user to click in the browser
    # The user's click was blocked; only the Executor clicked: once.
    assert clicks(shop)["fav"] == 1
    assert shop.locator("#er-point-banner").count() == 0


def test_timeout_while_waiting_for_the_click(shop):
    user = FakeUser(UserChoice("point"))
    executor = ActionExecutor(shop, disambiguator=user, can_point=True, point_timeout_s=0.3)
    result = executor.click("marcar a caneca como favorita")

    assert result.resolved_by == "user_skipped"
    assert clicks(shop)["fav"] == 0


def test_terminal_repeats_the_question_until_a_valid_answer(shop):
    answers = iter(["9", "talvez", "2"])
    out = []
    ui = TerminalDisambiguator(open_screenshot=False, input_fn=lambda _: next(answers), output=out.append)
    result = ActionExecutor(shop, disambiguator=ui).click("adicionar ao carrinho")

    assert result.status == "success"
    assert sum(clicks(shop).values()) == 1
    text = "\n".join(out)
    assert "more than one possible element" in text
    assert "[1] Button" in text and "[2] Button" in text
    assert text.count("not recognized") == 2



def test_terminal_messages_in_portuguese(monkeypatch):
    from anchor.engine.disambiguation import TerminalDisambiguator
    from anchor.engine.disambiguation.types import CandidateView, ChoiceRequest

    monkeypatch.setenv("ANCHOR_LANG", "pt")
    printed, answers = [], iter(["x", "p"])
    terminal = TerminalDisambiguator(open_screenshot=False, input_fn=lambda _: next(answers), output=printed.append)
    request = ChoiceRequest(action="click", description="Salvar", reason="ambiguous", can_point=False, screenshot=None,
                            candidates=[CandidateView(1, "Botão", "Salvar", ""), CandidateView(2, "Botão", "Salvar", "")])
    assert terminal.choose(request).kind == "skip"
    text = "\n".join(printed)
    assert "Encontrei mais de um elemento" in text and "Resposta não reconhecida" in text
