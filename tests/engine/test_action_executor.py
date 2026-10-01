from unittest.mock import Mock

from anchor.engine.action_executor import (
    ActionExecutor,
    ActionResult,
)
from anchor.engine.element_resolver import Match


def make_match(
    page,
    score: float,
    text: str = "Botão",
    role: str = "button",
):
    locator = Mock()
    page.locator.return_value = locator

    match = Match(
        id=f"test-{score}",
        tag="button",
        role=role,
        label="",
        text=text,
        content=text,
        context="",
        rect={
            "x": 0,
            "y": 0,
            "width": 100,
            "height": 40,
        },
        score=score,
        page=page,
    )

    return match, locator


def make_executor(
    score: float = 0.90,
    text: str = "Elemento",
    role: str = "button",
):
    page = Mock()
    resolver = Mock()

    match, locator = make_match(
        page,
        score=score,
        text=text,
        role=role,
    )

    resolver.query.return_value = [match]

    executor = ActionExecutor(
        page,
        resolver=resolver,
    )

    return executor, match, locator


# ============================================================
# CLICK
# ============================================================


def test_click_success():
    """
    Must perform the action when there is a single
    reliable candidate.
    """

    executor, match, locator = make_executor(
        score=0.90,
        text="Adicionar ao carrinho",
    )

    result = executor.click(
        "botão para adicionar ao carrinho"
    )

    assert isinstance(result, ActionResult)
    assert result.status == "success"
    assert result.selected_element == match
    assert result.score == 0.90

    locator.click.assert_called_once()


def test_click_ambiguous():
    """
    Must prevent the execution when the two best
    candidates have very close scores.
    """

    page = Mock()
    resolver = Mock()

    first, first_locator = make_match(
        page,
        score=0.80,
        text="Adicionar ao carrinho",
    )

    second, second_locator = make_match(
        page,
        score=0.76,
        text="Adicionar ao carrinho",
    )

    resolver.query.return_value = [
        first,
        second,
    ]

    executor = ActionExecutor(
        page,
        resolver=resolver,
        ambiguity_gap=0.08,
    )

    result = executor.click(
        "botão para adicionar ao carrinho"
    )

    assert result.status == "ambiguous"
    assert result.selected_element is None
    assert result.candidates == [
        first,
        second,
    ]

    first_locator.click.assert_not_called()
    second_locator.click.assert_not_called()


def test_click_not_found():
    """
    Must return not_found when there is no
    reliable candidate.
    """

    executor, match, locator = make_executor(
        score=0.10,
        text="Elemento irrelevante",
    )

    result = executor.click(
        "botão inexistente"
    )

    assert result.status == "not_found"
    assert result.selected_element is None
    assert result.candidates == [match]

    locator.click.assert_not_called()


def test_click_error():
    """
    Must return error when the element was found,
    but performing the action failed.
    """

    executor, match, locator = make_executor(
        score=0.90,
        text="Adicionar ao carrinho",
    )

    locator.click.side_effect = Exception(
        "Elemento não está mais disponível"
    )

    result = executor.click(
        "botão para adicionar ao carrinho"
    )

    assert result.status == "error"
    assert result.selected_element == match
    assert result.score == 0.90
    assert (
        result.error
        == "Elemento não está mais disponível"
    )


# ============================================================
# HOVER
# ============================================================


def test_hover_success():
    """
    Must hover over the resolved element.
    """

    executor, match, locator = make_executor(
        text="Menu",
    )

    result = executor.hover(
        "menu principal"
    )

    assert result.status == "success"
    assert result.selected_element == match
    assert result.score == 0.90

    locator.hover.assert_called_once()


# ============================================================
# CHECK
# ============================================================


def test_check_success():
    """
    Must check the checkbox found.
    """

    executor, match, locator = make_executor(
        text="Aceito os termos",
        role="checkbox",
    )

    result = executor.check(
        "checkbox para aceitar os termos"
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.check.assert_called_once()


# ============================================================
# UNCHECK
# ============================================================


def test_uncheck_success():
    """
    Must uncheck the checkbox found.
    """

    executor, match, locator = make_executor(
        text="Aceito os termos",
        role="checkbox",
    )

    result = executor.uncheck(
        "checkbox para aceitar os termos"
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.uncheck.assert_called_once()


# ============================================================
# PRESS
# ============================================================


def test_press_success():
    """
    Must press the given key.
    """

    executor, match, locator = make_executor(
        text="Campo de busca",
        role="textbox",
    )

    result = executor.press(
        "campo de busca",
        "Enter",
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.press.assert_called_once_with(
        "Enter",
    )


# ============================================================
# FILL
# ============================================================


def test_fill_success():
    """
    Must fill the element with the given text.
    """

    executor, match, locator = make_executor(
        text="Campo de usuário",
        role="textbox",
    )

    result = executor.fill(
        "campo de usuário",
        "lucas@example.com",
    )

    assert result.status == "success"
    assert result.selected_element == match
    assert result.score == 0.90

    locator.fill.assert_called_once_with(
        "lucas@example.com",
    )


# ============================================================
# SELECT
# ============================================================


def test_select_by_value():
    """
    Must select an option by value.
    """

    executor, match, locator = make_executor(
        text="Ordenação",
        role="combobox",
    )

    result = executor.select(
        "campo de ordenação",
        value="price-low-to-high",
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.select_option.assert_called_once_with(
        value="price-low-to-high",
    )


def test_select_by_label():
    """
    Must select an option by label.
    """

    executor, match, locator = make_executor(
        text="Ordenação",
        role="combobox",
    )

    result = executor.select(
        "campo de ordenação",
        label="Preço: menor para maior",
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.select_option.assert_called_once_with(
        label="Preço: menor para maior",
    )


def test_select_by_index():
    """
    Must select an option by index.
    """

    executor, match, locator = make_executor(
        text="Ordenação",
        role="combobox",
    )

    result = executor.select(
        "campo de ordenação",
        index=2,
    )

    assert result.status == "success"
    assert result.selected_element == match

    locator.select_option.assert_called_once_with(
        index=2,
    )


def test_select_without_option():
    """
    Must return error when no selection
    method was given.
    """

    executor, match, locator = make_executor(
        text="Ordenação",
        role="combobox",
    )

    result = executor.select(
        "campo de ordenação",
    )

    assert result.status == "error"
    assert result.selected_element == match
    assert result.score == 0.90
    assert (
        result.error
        == "select() requer value, label ou index"
    )

    locator.select_option.assert_not_called()


# ============================================================
# EXTRACTION
# ============================================================


def test_extract_text_success():
    """
    Must extract the element's inner text.
    """

    executor, match, locator = make_executor(
        text="Nome do produto",
    )

    locator.inner_text.return_value = (
        "Sauce Labs Backpack"
    )

    result = executor.extract_text(
        "nome do produto"
    )

    assert result.status == "success"
    assert result.selected_element == match
    assert result.value == "Sauce Labs Backpack"

    locator.inner_text.assert_called_once()


def test_extract_attribute_success():
    """
    Must extract an attribute of the element.
    """

    executor, match, locator = make_executor(
        text="Link do produto",
        role="link",
    )

    locator.get_attribute.return_value = (
        "/inventory-item.html?id=4"
    )

    result = executor.extract_attribute(
        "link do produto",
        "href",
    )

    assert result.status == "success"
    assert result.selected_element == match
    assert (
        result.value
        == "/inventory-item.html?id=4"
    )

    locator.get_attribute.assert_called_once_with(
        "href",
    )


def test_extract_value_success():
    """
    Must extract the value of a field.
    """

    executor, match, locator = make_executor(
        text="Campo de usuário",
        role="textbox",
    )

    locator.input_value.return_value = (
        "lucas@example.com"
    )

    result = executor.extract_value(
        "campo de usuário"
    )

    assert result.status == "success"
    assert result.selected_element == match
    assert result.value == "lucas@example.com"

    locator.input_value.assert_called_once()