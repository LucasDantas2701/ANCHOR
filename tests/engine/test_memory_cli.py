"""Tests of the memory review command (python -m anchor.engine.memory)."""

import time

import pytest

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import UserChoice
from anchor.engine.memory import ChoiceMemory
from anchor.engine.memory.cli import main

URL = "https://loja.exemplo/produtos"


def sig(role, text, context=""):
    return {"role": role, "tag": "button" if role == "button" else "a",
            "label": "", "text": text, "hint": "", "test_id": "", "context": context}


@pytest.fixture
def memory_file(tmp_path):
    path = tmp_path / "memoria.json"
    memory = ChoiceMemory(path)
    memory.remember(URL, "click", "adicionar ao carrinho", sig("button", "Add to cart", "UltraBook 14 $899.00"))
    time.sleep(1.1)  # "created" has a resolution of seconds: this guarantees the order
    memory.remember(URL, "click", "marcar a cafeteira como favorita", sig("link", "Wishlist", "TechStore 2 Sign in"))
    return path


def run(argv, answers=()):
    out = []
    answers = iter(answers)
    code = main([str(a) for a in argv], input_fn=lambda _: next(answers), out=out.append)
    return code, "\n".join(out)


def test_list_shows_numbered_choices(memory_file):
    code, text = run([memory_file, "listar"])
    assert code == 0
    assert '[1] Step: "adicionar ao carrinho"' in text
    assert '[2] Step: "marcar a cafeteira como favorita"' in text
    assert 'Link "Wishlist"' in text
    assert "near: UltraBook 14 $899.00" in text


def test_forget_one_item(memory_file):
    code, text = run([memory_file, "esquecer", 2])
    assert code == 0
    assert "Forgotten [2]" in text
    remaining = ChoiceMemory(memory_file).ordered()
    assert [e.description for _, e in remaining] == ["adicionar ao carrinho"]


def test_forget_invalid_number_deletes_nothing(memory_file):
    code, text = run([memory_file, "esquecer", 7])
    assert code == 1
    assert "Invalid" in text
    assert len(ChoiceMemory(memory_file).entries) == 2


def test_clear_asks_for_confirmation(memory_file):
    code, text = run([memory_file, "limpar"], answers=["n"])
    assert "Nothing was deleted" in text
    assert len(ChoiceMemory(memory_file).entries) == 2

    code, text = run([memory_file, "limpar"], answers=["s"])
    assert "2 choice(s) forgotten" in text
    assert ChoiceMemory(memory_file).entries == {}


def test_clear_without_confirmation(memory_file):
    run([memory_file, "limpar", "--sim"])
    assert ChoiceMemory(memory_file).entries == {}


def test_missing_file(tmp_path):
    code, text = run([tmp_path / "nao_existe.json", "listar"])
    assert code == 1
    assert "not found" in text


# --------------------------------------------------------------------------
# Full scenario: a wrong remembered choice, fixed with the command.
# --------------------------------------------------------------------------

PAGE = """
<html><body>
  <header><a href="#w" id="wish">Wishlist</a></header>
  <div class="card"><h3>Barista Coffee Maker</h3>
    <button id="heart" aria-label="Add to wishlist" style="width:20px;height:20px"></button></div>
</body></html>
"""


class Scripted:
    def __init__(self, choice_fn):
        self.choice_fn = choice_fn
        self.asked = 0

    def choose(self, request):
        self.asked += 1
        return self.choice_fn(request)

    def notify(self, message):
        pass


def test_wrong_choice_is_fixed_after_being_forgotten(page, tmp_path):
    path = tmp_path / "memoria.json"
    step = "marcar a cafeteira como favorita"
    page.set_content(PAGE)

    # 1st run: the user picks the wrong link ("Wishlist" in the header).
    wrong = Scripted(lambda r: UserChoice("candidate", next(c.number for c in r.candidates if c.name == "Wishlist")))
    ActionExecutor(page, disambiguator=wrong, memory=ChoiceMemory(path)).click(step)

    # 2nd run: the memory repeats the mistake, without asking.
    nobody = Scripted(lambda r: pytest.fail("não deveria perguntar"))
    again = ActionExecutor(page, disambiguator=nobody, memory=ChoiceMemory(path)).click(step)
    assert again.resolved_by == "memory"
    assert again.selected_element.text == "Wishlist"
    assert again.score is None and again.similarity > 0

    # The user reviews and forgets the wrong choice.
    code, _ = run([path, "esquecer", 1])
    assert code == 0

    # 3rd run: the assistant asks again, and the user picks the right one.
    right = Scripted(lambda r: UserChoice("candidate", next(c.number for c in r.candidates if c.name == "Add to wishlist")))
    fixed = ActionExecutor(page, disambiguator=right, memory=ChoiceMemory(path)).click(step)
    assert right.asked == 1
    assert fixed.resolved_by == "user"
    assert fixed.selected_element.label == "Add to wishlist"


def test_memory_drops_the_least_recently_used_choice(tmp_path):
    memory = ChoiceMemory(tmp_path / "m.json", max_entries=3)
    for i in range(3):
        memory.remember(URL, "click", f"passo {i}", sig("button", f"B{i}"))
        memory.entries[next(k for k in memory.entries if k.endswith(f"passo {i}"))].last_used = f"2026-01-0{i + 1}T00:00:00"
    memory.mark_used(URL, "click", "passo 0")          # step 0 becomes the most recent again
    memory.remember(URL, "click", "passo 3", sig("button", "B3"))

    kept = sorted(e.description for e in ChoiceMemory(tmp_path / "m.json").entries.values())
    assert kept == ["passo 0", "passo 2", "passo 3"]   # step 1, the least recently used, was dropped



def test_english_commands_and_confirmation(memory_file):
    code, text = run([memory_file, "list"])
    assert code == 0 and "[1] Step" in text
    code, text = run([memory_file, "clear"], answers=["y"])
    assert code == 0 and ChoiceMemory(memory_file).entries == {}
