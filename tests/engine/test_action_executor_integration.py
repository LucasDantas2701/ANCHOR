import pytest

from anchor.engine.action_executor import ActionExecutor


@pytest.fixture
def product_page(page):
    page.set_content(
        """
        <!DOCTYPE html>
        <html>
        <body>

            <div class="product">
                <h2>Produto A</h2>
                <button>
                    Adicionar ao carrinho
                </button>
            </div>

            <div class="product">
                <h2>Produto A</h2>
                <button>
                    Adicionar ao carrinho
                </button>
            </div>

        </body>
        </html>
        """
    )

    return page

def test_click_product_button_is_ambiguous(product_page):
    """
    Quando existem dois elementos semanticamente equivalentes,
    o Executor deve evitar escolher arbitrariamente entre eles.
    """

    executor = ActionExecutor(
        product_page,
        ambiguity_gap=0.08,
    )

    result = executor.click(
        "botão para adicionar ao carrinho"
    )

    assert result.status == "ambiguous"

    assert result.selected_element is None

    assert result.candidates is not None
    assert len(result.candidates) >= 2

    assert product_page.locator("button").count() == 2


def test_click_unique_product_button(product_page):
    """
    Quando existe apenas um botão compatível com a
    descrição, o Executor deve executá-lo.
    """

    product_page.locator(
        ".product"
    ).nth(1).evaluate(
        "(element) => element.remove()"
    )

    executor = ActionExecutor(
        product_page,
        ambiguity_gap=0.08,
    )

    result = executor.click(
        "botão para adicionar a mochila ao carrinho"
    )

    assert result.status == "success"

    assert result.selected_element is not None

    assert result.selected_element.score >= 0.20


def test_fill_real_input(page):
    """
    Testa a integração Resolver + Executor com um
    campo de entrada real.
    """

    page.set_content(
        """
        <html>
        <body>

            <label for="username">
                Nome de usuário
            </label>

            <input
                id="username"
                type="text"
            >

        </body>
        </html>
        """
    )

    executor = ActionExecutor(page)

    result = executor.fill(
        "campo para nome de usuário",
        "Lucas",
    )

    assert result.status == "success"

    assert page.locator(
        "#username"
    ).input_value() == "Lucas"


def test_extract_real_text(page):
    """
    Testa a integração Resolver + Executor com
    extração de texto real.
    """

    page.set_content(
        """
        <html>
        <body>

            <h1>
                Sauce Labs Backpack
            </h1>

        </body>
        </html>
        """
    )

    executor = ActionExecutor(page)

    result = executor.extract_text(
        "Sauce Labs Backpack"
    )

    assert result.status == "success"

    assert result.value == (
        "Sauce Labs Backpack"
    )