"""The interventions experiment's simulated user, and the user's wait measured apart."""

import time

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.memory import ChoiceMemory
from eval.interventions import OracleExecutor

MUGS = """<html><body>
  <div><h3>Caneca azul</h3><button class="azul">Adicionar</button></div>
  <div><h3>Caneca verde</h3><button class="verde">Adicionar</button></div></body></html>"""


def test_the_oracle_picks_the_right_candidate_and_the_memory_keeps_it(page, tmp_path):
    memory = ChoiceMemory(tmp_path / "m.json")
    page.set_content(MUGS)
    first = OracleExecutor(page, "button.verde", memory=memory)
    result = first.hover("Adicionar")
    assert first.asked == 1 and result.selected_element.text == "Adicionar"
    assert page.evaluate("document.querySelector('.verde').dataset.erId") == result.selected_element.id
    page.set_content(MUGS)
    second = OracleExecutor(page, "button.verde", memory=memory)
    result = second.hover("Adicionar")
    assert second.asked == 0 and result.resolved_by == "memory"


def test_the_oracle_clicks_the_element_when_it_is_not_among_the_candidates(page, tmp_path):
    page.set_content("""<html><body><button>Salvar</button><button>Salvar rascunho</button>
        <span class="heart">♥</span></body></html>""")          # not indexed: not clickable-looking
    oracle = OracleExecutor(page, "span.heart", memory=ChoiceMemory(tmp_path / "m.json"))
    oracle.hover("marcar como favorito")
    assert oracle.asked == 1 and oracle.pointed == 1


class SlowUser:
    def choose(self, request):
        from anchor.engine.disambiguation import UserChoice
        time.sleep(0.3)
        return UserChoice("candidate", 1)

    def notify(self, message):
        pass


def test_the_users_wait_is_measured_apart(page):
    page.set_content(MUGS)
    executor = ActionExecutor(page, disambiguator=SlowUser())
    executor.hover("Adicionar")
    assert 0.3 <= executor.user_wait_s < 2
