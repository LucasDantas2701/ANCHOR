"""Layer 4: a screenshot can confirm a step the other checks doubted, never the opposite."""

from types import SimpleNamespace

from anchor.agent import Agent
from anchor.agent.vision import VisionChecker
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step


class FakeVision:
    """Answers every question with `answer` and records what it was asked."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []
        self.checks, self.seconds, self.language = 0, 0.0, "pt"

    def capture(self, page):
        return "img"

    def _ask(self, kind, *args):
        self.checks += 1
        self.asked.append((kind,) + args)
        return self.answer

    def shows_state(self, page, action, description, value):
        return self._ask("state", action, description, value)

    def shows_text(self, page, text):
        return self._ask("text", text)

    def changed(self, before, page, description):
        return self._ask("changed", description)


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def run(page, html, step, vision, request="faça a tarefa da página"):
    page.set_content(html)
    page.set_default_timeout(1500)
    return Agent(page, OnePlan(step), ActionExecutor(page), report=None, vision=vision).run(request)


CLEARS_ITSELF = '<html><body><label for="n">Nome</label><input id="n" oninput="this.value=\'\'"></body></html>'
DEAD_BUTTON = "<html><body><button>Continuar</button></body></html>"


def test_a_state_the_code_doubts_is_confirmed_by_the_screenshot(page):
    vision = FakeVision(True)
    result = run(page, CLEARS_ITSELF, ("fill", "Nome", "Ana"), vision, request="preencha a Ana")
    assert result.ok and result.vision_confirmed == 1 and result.vision_checks == 1
    assert vision.asked[0] == ("state", "fill", "Nome", "Ana")


def test_when_the_screenshot_does_not_confirm_the_step_fails(page):
    result = run(page, CLEARS_ITSELF, ("fill", "Nome", "Ana"), FakeVision(False), request="preencha a Ana")
    assert not result.ok and result.vision_confirmed == 0


def test_an_unclear_answer_does_not_confirm(page):
    result = run(page, CLEARS_ITSELF, ("fill", "Nome", "Ana"), FakeVision(None), request="preencha a Ana")
    assert not result.ok


def test_a_click_without_effect_in_the_code_is_confirmed_by_comparing_screenshots(page):
    vision = FakeVision(True)
    result = run(page, DEAD_BUTTON, ("click", "Continuar", None), vision)
    assert result.ok and result.no_effect == 0 and vision.asked[0][0] == "changed"


def test_an_expected_text_seen_only_in_the_screenshot_is_not_a_suspicion(page):
    html = """<html><body><button onclick="document.body.appendChild(document.createElement('canvas'))">
        Salvar</button></body></html>"""          # the confirmation is drawn, not written
    vision = FakeVision(True)
    result = run(page, html, ("click", "Salvar", None, None, "Cadastro salvo"), vision, request="salve")
    assert result.ok and result.suspicions == 0 and vision.asked == [("text", "Cadastro salvo")]


def test_an_error_message_is_never_overruled(page):
    html = """<html><body><button onclick="document.getElementById('m').textContent='CPF inválido'">Salvar</button>
        <p id="m" role="alert"></p></body></html>"""
    vision = FakeVision(True)
    result = run(page, html, ("click", "Salvar", None), vision, request="salve")
    assert not result.ok and vision.asked == []


def test_without_vision_nothing_changes(page):
    result = run(page, CLEARS_ITSELF, ("fill", "Nome", "Ana"), None, request="preencha a Ana")
    assert not result.ok and result.vision_checks == 0


def test_the_checker_reads_yes_no_and_errors():
    def client(text=None, error=False):
        def create(**kwargs):
            if error:
                raise RuntimeError("offline")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    assert VisionChecker(client("Sim."), "m").ask("q", ["img"]) is True
    assert VisionChecker(client("no"), "m").ask("q", ["img"]) is False
    assert VisionChecker(client("talvez"), "m").ask("q", ["img"]) is None
    assert VisionChecker(client(error=True), "m").ask("q", ["img"]) is None       # an error is "not confirmed"
    assert VisionChecker(client("sim"), "m").ask("q", [None]) is None              # no screenshot, no answer
