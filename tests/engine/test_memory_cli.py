"""Testes do comando de revisão da memória (python -m app.engine.memory)."""

import time

import pytest

from app.engine.action_executor import ActionExecutor
from app.engine.disambiguation import UserChoice
from app.engine.memory import ChoiceMemory
from app.engine.memory.cli import main

URL = "https://loja.exemplo/produtos"


def sig(role, text, context=""):
    return {"role": role, "tag": "button" if role == "button" else "a",
            "label": "", "text": text, "hint": "", "test_id": "", "context": context}


@pytest.fixture
def memory_file(tmp_path):
    path = tmp_path / "memoria.json"
    memory = ChoiceMemory(path)
    memory.remember(URL, "click", "adicionar ao carrinho", sig("button", "Add to cart", "UltraBook 14 $899.00"))
    time.sleep(1.1)  # "created" tem resolução de segundos: garante a ordem
    memory.remember(URL, "click", "marcar a cafeteira como favorita", sig("link", "Wishlist", "TechStore 2 Sign in"))
    return path


def run(argv, answers=()):
    out = []
    answers = iter(answers)
    code = main([str(a) for a in argv], input_fn=lambda _: next(answers), out=out.append)
    return code, "\n".join(out)


def test_listar_mostra_as_escolhas_numeradas(memory_file):
    code, text = run([memory_file, "listar"])
    assert code == 0
    assert '[1] Passo: "adicionar ao carrinho"' in text
    assert '[2] Passo: "marcar a cafeteira como favorita"' in text
    assert 'Link "Wishlist"' in text
    assert "perto de: UltraBook 14 $899.00" in text


def test_esquecer_um_item(memory_file):
    code, text = run([memory_file, "esquecer", 2])
    assert code == 0
    assert "Esquecida [2]" in text
    remaining = ChoiceMemory(memory_file).ordered()
    assert [e.description for _, e in remaining] == ["adicionar ao carrinho"]


def test_esquecer_numero_invalido_nao_apaga_nada(memory_file):
    code, text = run([memory_file, "esquecer", 7])
    assert code == 1
    assert "inválido" in text
    assert len(ChoiceMemory(memory_file).entries) == 2


def test_limpar_pede_confirmacao(memory_file):
    code, text = run([memory_file, "limpar"], answers=["n"])
    assert "Nada foi apagado" in text
    assert len(ChoiceMemory(memory_file).entries) == 2

    code, text = run([memory_file, "limpar"], answers=["s"])
    assert "2 escolha(s) esquecida(s)" in text
    assert ChoiceMemory(memory_file).entries == {}


def test_limpar_sem_confirmacao(memory_file):
    run([memory_file, "limpar", "--sim"])
    assert ChoiceMemory(memory_file).entries == {}


def test_arquivo_inexistente(tmp_path):
    code, text = run([tmp_path / "nao_existe.json", "listar"])
    assert code == 1
    assert "não encontrado" in text


# --------------------------------------------------------------------------
# Cenário completo: escolha errada memorizada, corrigida pelo comando.
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


def test_escolha_errada_e_corrigida_depois_de_esquecida(page, tmp_path):
    path = tmp_path / "memoria.json"
    step = "marcar a cafeteira como favorita"
    page.set_content(PAGE)

    # 1ª execução: o usuário escolhe o link errado ("Wishlist" do cabeçalho).
    wrong = Scripted(lambda r: UserChoice("candidate", next(c.number for c in r.candidates if c.name == "Wishlist")))
    ActionExecutor(page, disambiguator=wrong, memory=ChoiceMemory(path)).click(step)

    # 2ª execução: a memória repete o erro, sem perguntar.
    nobody = Scripted(lambda r: pytest.fail("não deveria perguntar"))
    again = ActionExecutor(page, disambiguator=nobody, memory=ChoiceMemory(path)).click(step)
    assert again.resolved_by == "memory"
    assert again.selected_element.text == "Wishlist"
    assert again.score is None and again.similarity > 0

    # O usuário revisa e esquece a escolha errada.
    code, _ = run([path, "esquecer", 1])
    assert code == 0

    # 3ª execução: o assistente volta a perguntar, e o usuário escolhe o certo.
    right = Scripted(lambda r: UserChoice("candidate", next(c.number for c in r.candidates if c.name == "Add to wishlist")))
    fixed = ActionExecutor(page, disambiguator=right, memory=ChoiceMemory(path)).click(step)
    assert right.asked == 1
    assert fixed.resolved_by == "user"
    assert fixed.selected_element.label == "Add to wishlist"


def test_memoria_descarta_a_escolha_usada_ha_mais_tempo(tmp_path):
    memory = ChoiceMemory(tmp_path / "m.json", max_entries=3)
    for i in range(3):
        memory.remember(URL, "click", f"passo {i}", sig("button", f"B{i}"))
        memory.entries[next(k for k in memory.entries if k.endswith(f"passo {i}"))].last_used = f"2026-01-0{i + 1}T00:00:00"
    memory.mark_used(URL, "click", "passo 0")          # o passo 0 volta a ser o mais recente
    memory.remember(URL, "click", "passo 3", sig("button", "B3"))

    kept = sorted(e.description for e in ChoiceMemory(tmp_path / "m.json").entries.values())
    assert kept == ["passo 0", "passo 2", "passo 3"]   # saiu o passo 1, o usado há mais tempo
