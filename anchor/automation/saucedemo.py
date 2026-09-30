"""
LEGADO: automação do SauceDemo com seletores fixos.

Mantida como exemplo do "antes" (RPA tradicional). A versão com o motor
semântico está em anchor/main.py.
"""

from playwright.sync_api import Page

from anchor.actions.extraction import extract_text
from anchor.actions.interaction import click
from anchor.actions.navigation import navigate
from anchor.actions.wait import wait_for_element


def run_saucedemo(page: Page) -> None:

    # Página de produtos
    navigate(page, "https://www.saucedemo.com/inventory.html")

    wait_for_element(page, ".inventory_list")

    print("Página de produtos carregada.")

    # Adiciona um produto ao carrinho
    click(
        page,
        '[data-test="add-to-cart-sauce-labs-backpack"]'
    )

    print("Produto adicionado ao carrinho.")

    # Abre o carrinho
    click(
        page,
        '[data-test="shopping-cart-link"]'
    )

    wait_for_element(
        page,
        ".cart_item"
    )

    # Extrai o nome do produto
    product_name = extract_text(
        page,
        ".inventory_item_name"
    )

    print(f"Produto no carrinho: {product_name}")