import pytest

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver

SAUCEDEMO_URL = "https://www.saucedemo.com"

# Vocabulário específico do site. Antes ficava no constants.py
# (viés de overfitting); agora é passado ao Resolver, como será
# feito com os dados de cada automação salva.
SAUCEDEMO_VOCAB = {
    "mochila": "backpack",
    "lanterna": "light",
    "bicicleta": "bike",
    "camiseta": "shirt",
    "jaqueta": "jacket",
    "macacão": "onesie",
}


@pytest.fixture
def saucedemo_page(page):
    page.goto(SAUCEDEMO_URL)

    page.locator(
        '[data-test="username"]'
    ).fill("standard_user")

    page.locator(
        '[data-test="password"]'
    ).fill("secret_sauce")

    page.locator(
        '[data-test="login-button"]'
    ).click()

    page.locator(".inventory_list").wait_for(
        state="visible"
    )

    return page


def test_add_backpack_to_cart(saucedemo_page):
    """
    Testa o fluxo completo:

        página real
            ↓
        ElementResolver
            ↓
        ActionExecutor
            ↓
        botão correto
            ↓
        produto no carrinho
    """

    executor = ActionExecutor(
        saucedemo_page,
        resolver=ElementResolver(saucedemo_page, synonyms=SAUCEDEMO_VOCAB),
    )

    result = executor.click(
        "botão para adicionar a mochila ao carrinho"
    )

    print("\nResultado:", result)

    assert result.status == "success"

    cart_badge = saucedemo_page.locator(
        ".shopping_cart_badge"
    )

    assert cart_badge.inner_text() == "1"


def test_find_backpack(saucedemo_page):
    """
    Testa apenas a capacidade do Resolver de encontrar
    o produto correto na página real.
    """

    executor = ActionExecutor(
        saucedemo_page,
    )

    result = executor.extract_text(
        "Sauce Labs Backpack"
    )

    print("\nResultado:", result)

    assert result.status == "success"

    assert (
        result.value
        == "Sauce Labs Backpack"
    )
def test_debug_backpack_candidates(saucedemo_page):
    from anchor.engine.element_resolver import ElementResolver

    resolver = ElementResolver(saucedemo_page, synonyms=SAUCEDEMO_VOCAB)

    matches = resolver.query(
        "botão para adicionar a mochila ao carrinho",
        k=10,
        action="click",
    )

    for i, match in enumerate(matches, 1):
        print("\n" + "=" * 60)
        print(f"CANDIDATO {i}")
        print("=" * 60)
        print("Score:", match.score)
        print("Tag:", match.tag)
        print("Role:", match.role)
        print("Label:", repr(match.label))
        print("Text:", repr(match.text))
        print("Content:", repr(match.content))
        print("Context:", repr(match.context))
def test_debug_backpack_text_candidates(saucedemo_page):
    from anchor.engine.element_resolver import ElementResolver

    resolver = ElementResolver(saucedemo_page)

    matches = resolver.query(
        "Sauce Labs Backpack",
        k=10,
        action="extract",
    )

    for i, match in enumerate(matches, 1):
        print("\n" + "=" * 60)
        print(f"CANDIDATO {i}")
        print("=" * 60)
        print("Score:", match.score)
        print("Tag:", match.tag)
        print("Role:", match.role)
        print("Label:", repr(match.label))
        print("Text:", repr(match.text))
        print("Content:", repr(match.content))
        print("Context:", repr(match.context))