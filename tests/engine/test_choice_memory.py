"""
Tests of the choice memory: the user disambiguates once, and the next
runs of the same step use the choice without asking.
"""

import json

import pytest

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import UserChoice
from anchor.engine.memory import ChoiceMemory


def shop_html(products, disabled=()):
    cards = "".join(
        f'<div class="product"><h2>{name}</h2>'
        f'<button id="{bid}" onclick="clicks[\'{bid}\']=(clicks[\'{bid}\']||0)+1"'
        f'{" disabled" if bid in disabled else ""}>Adicionar ao carrinho</button></div>'
        for name, bid in products
    )
    return f"<html><body><script>window.clicks={{}};</script>{cards}</body></html>"


AZUL, VERDE, PRETA = ("Caneca azul", "azul"), ("Caneca verde", "verde"), ("Caneca preta", "preta")
STEP = "adicionar ao carrinho"


class FakeUser:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = 0

    def choose(self, request):
        self.asked += 1
        if not self.answers:
            raise AssertionError("o usuário não deveria ter sido consultado")
        return self.answers.pop(0)

    def notify(self, message):
        pass


def pick(request_text, color):
    """Number of the candidate whose 'near' text contains the color."""
    return next(c.number for c in request_text.candidates if color in c.near)


class PickColor(FakeUser):
    def __init__(self, color):
        super().__init__()
        self.color = color

    def choose(self, request):
        self.asked += 1
        return UserChoice("candidate", pick(request, self.color))


@pytest.fixture
def memory(tmp_path):
    return ChoiceMemory(tmp_path / "memoria.json")


def clicks(page):
    return page.evaluate("window.clicks")


def run(page, memory, user):
    return ActionExecutor(page, disambiguator=user, memory=memory).click(STEP)


def test_user_choice_is_remembered(page, memory):
    page.set_content(shop_html([AZUL, VERDE]))
    first = run(page, memory, PickColor("verde"))
    assert first.resolved_by == "user"
    assert clicks(page) == {"verde": 1}
    assert len(memory.entries) == 1

    page.set_content(shop_html([AZUL, VERDE]))
    user = FakeUser()  # fails if consulted
    second = run(page, memory, user)
    assert second.status == "success"
    assert second.resolved_by == "memory"
    assert user.asked == 0
    assert clicks(page) == {"verde": 1}


def test_memory_persists_to_a_file(page, tmp_path):
    path = tmp_path / "memoria.json"
    page.set_content(shop_html([AZUL, VERDE]))
    run(page, ChoiceMemory(path), PickColor("azul"))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["entries"]) == 1

    page.set_content(shop_html([AZUL, VERDE]))
    result = run(page, ChoiceMemory(path), FakeUser())  # new instance, reads from the file
    assert result.resolved_by == "memory"
    assert clicks(page) == {"azul": 1}


def test_finds_the_element_again_even_if_the_order_changes(page, memory):
    page.set_content(shop_html([AZUL, VERDE, PRETA]))
    run(page, memory, PickColor("verde"))

    page.set_content(shop_html([PRETA, VERDE, AZUL]))  # another order
    result = run(page, memory, FakeUser())
    assert result.resolved_by == "memory"
    assert clicks(page) == {"verde": 1}


def test_missing_element_asks_again_and_expires(page, memory):
    page.set_content(shop_html([AZUL, VERDE]))
    run(page, memory, PickColor("verde"))

    # The green mug left the page: the memory does not help, the user is asked.
    for attempt in range(memory.max_misses):
        page.set_content(shop_html([AZUL, PRETA]))
        user = FakeUser(UserChoice("skip"))
        result = run(page, memory, user)
        assert result.resolved_by == "user_skipped"
        assert user.asked == 1

    assert memory.entries == {}  # forgotten after max_misses misses in a row


def test_action_failing_with_a_remembered_choice_forgets_it(page, memory):
    page.set_content(shop_html([AZUL, VERDE]))
    run(page, memory, PickColor("verde"))

    page.set_content(shop_html([AZUL, VERDE], disabled={"verde"}))
    result = ActionExecutor(page, disambiguator=FakeUser(), memory=memory).click(STEP, timeout=500)
    assert result.status == "error"
    assert result.resolved_by == "memory"
    assert memory.entries == {}


def test_skipping_is_not_remembered(page, memory):
    page.set_content(shop_html([AZUL, VERDE]))
    run(page, memory, FakeUser(UserChoice("skip")))
    assert memory.entries == {}


def test_choice_by_clicking_on_the_page_is_remembered(page, memory):
    page.set_content(
        "<html><body><script>window.clicks={};</script>"
        "<p>Caneca azul</p>"
        "<span id='fav' onclick=\"clicks.fav=(clicks.fav||0)+1\" "
        "style='display:inline-block;width:20px;height:20px;background:#c00'></span>"
        "</body></html>"
    )

    class PointUser(FakeUser):
        def choose(self, request):
            page.evaluate(
                "setTimeout(() => document.getElementById('fav')"
                ".dispatchEvent(new MouseEvent('click', {bubbles: true})), 200)"
            )
            return UserChoice("point")

    step = "marcar a caneca como favorita"
    first = ActionExecutor(page, disambiguator=PointUser(), can_point=True,
                           memory=memory, point_timeout_s=5).click(step)
    assert first.resolved_by == "user"
    assert len(memory.entries) == 1

    second = ActionExecutor(page, disambiguator=FakeUser(), memory=memory).click(step)
    assert second.resolved_by == "memory"
    assert clicks(page) == {"fav": 2}


def test_same_description_on_another_page_does_not_use_the_memory(page, memory, tmp_path):
    (tmp_path / "a.html").write_text(shop_html([AZUL, VERDE]), encoding="utf-8")
    (tmp_path / "b.html").write_text(shop_html([AZUL, VERDE]), encoding="utf-8")

    page.goto((tmp_path / "a.html").as_uri())
    run(page, memory, PickColor("verde"))

    page.goto((tmp_path / "b.html").as_uri())
    user = PickColor("azul")
    result = run(page, memory, user)
    assert user.asked == 1
    assert result.resolved_by == "user"
    assert len(memory.entries) == 2


def suggestions_html(items):
    options = "".join(
        f'<div role="option" onclick="window.escolhida=\'{t}\'" style="cursor:pointer">{t}</div>' for t in items
    )
    return (f'<html><body><input aria-label="Pesquisar" value="rpa em manaus">'
            f'<div role="listbox">{options}</div></body></html>')


def test_suggestion_chosen_by_click_is_found_again_among_others(page, memory):
    page.set_content(suggestions_html(["rpa em manaus", "rpa developer", "rpa uipath"]))

    class PointUser(FakeUser):
        def choose(self, request):
            page.evaluate(
                "setTimeout(() => [...document.querySelectorAll('[role=option]')]"
                ".find(e => e.textContent === 'rpa em manaus')"
                ".dispatchEvent(new MouseEvent('click', {bubbles: true})), 200)"
            )
            return UserChoice("point")

    step = "clicar na sugestão da pesquisa"
    first = ActionExecutor(page, disambiguator=PointUser(), can_point=True,
                           memory=memory, point_timeout_s=5).click(step)
    assert first.resolved_by == "user"
    saved = next(iter(memory.entries.values())).signature
    assert saved["role"] == "option" and saved["context"]   # full signature, with context

    # On the next search, the list is rebuilt: another order, other items.
    page.set_content(suggestions_html(["rpa junior", "rpa em manaus", "rpa remoto", "rpa senior"]))
    second = ActionExecutor(page, disambiguator=FakeUser(), memory=memory).click(step)
    assert second.resolved_by == "memory"
    assert page.evaluate("window.escolhida") == "rpa em manaus"
