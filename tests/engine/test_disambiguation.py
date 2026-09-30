"""
Testes do desempate pelo usuário.

Um "usuário falso" (FakeUser) substitui o terminal: ele responde
automaticamente e registra o que viu, para os testes conferirem.
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


def test_sem_desempate_mantem_comportamento_antigo(shop):
    result = ActionExecutor(shop).click("adicionar ao carrinho")
    assert result.status == "ambiguous"
    assert clicks(shop) == {"a": 0, "b": 0, "fav": 0}


def test_usuario_escolhe_o_segundo_candidato(shop):
    user = FakeUser(UserChoice("candidate", 2))
    result = ActionExecutor(shop, disambiguator=user).click("adicionar ao carrinho")

    assert result.status == "success"
    assert result.resolved_by == "user"
    request = user.requests[0]
    assert request.reason == "ambiguous"
    assert request.screenshot  # sem janela visível, vai uma imagem
    chosen = request.candidates[1]
    assert chosen.kind == "Botão"
    assert chosen.name == "Adicionar ao carrinho"
    assert sum(clicks(shop).values()) == 1
    target = "a" if "azul" in chosen.near else "b"
    assert clicks(shop)[target] == 1


def test_numeros_aparecem_na_pagina_e_somem_depois(shop):
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


def test_usuario_pula_o_passo(shop):
    user = FakeUser(UserChoice("skip"))
    result = ActionExecutor(shop, disambiguator=user).click("adicionar ao carrinho")

    assert result.status == "ambiguous"
    assert result.resolved_by == "user_skipped"
    assert clicks(shop) == {"a": 0, "b": 0, "fav": 0}


def test_usuario_clica_no_elemento_e_o_clique_nao_dispara_duas_vezes(shop):
    # Simula o clique do usuário no navegador logo depois da resposta "C".
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
    assert user.messages  # avisou para clicar no navegador
    # O clique do usuário foi bloqueado; só o Executor clicou: uma vez.
    assert clicks(shop)["fav"] == 1
    assert shop.locator("#er-point-banner").count() == 0


def test_tempo_esgotado_ao_esperar_o_clique(shop):
    user = FakeUser(UserChoice("point"))
    executor = ActionExecutor(shop, disambiguator=user, can_point=True, point_timeout_s=0.3)
    result = executor.click("marcar a caneca como favorita")

    assert result.resolved_by == "user_skipped"
    assert clicks(shop)["fav"] == 0


def test_terminal_repete_a_pergunta_ate_resposta_valida(shop):
    answers = iter(["9", "talvez", "2"])
    out = []
    ui = TerminalDisambiguator(open_screenshot=False, input_fn=lambda _: next(answers), output=out.append)
    result = ActionExecutor(shop, disambiguator=ui).click("adicionar ao carrinho")

    assert result.status == "success"
    assert sum(clicks(shop).values()) == 1
    text = "\n".join(out)
    assert "mais de um elemento" in text
    assert "[1] Botão" in text and "[2] Botão" in text
    assert text.count("não reconhecida") == 2
