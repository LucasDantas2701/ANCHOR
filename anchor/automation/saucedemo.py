"""
LEGACY: SauceDemo automation with fixed selectors.

Kept as an example of the "before" (traditional RPA). The version with the
semantic engine is in anchor/main.py.
"""

from playwright.sync_api import Page

from anchor.actions.extraction import extract_text
from anchor.actions.interaction import click
from anchor.actions.navigation import navigate
from anchor.actions.wait import wait_for_element


def run_saucedemo(page: Page) -> None:

    # Products page
    navigate(page, "https://www.saucedemo.com/inventory.html")

    wait_for_element(page, ".inventory_list")

    print("Products page loaded.")

    # Add a product to the cart
    click(
        page,
        '[data-test="add-to-cart-sauce-labs-backpack"]'
    )

    print("Product added to the cart.")

    # Open the cart
    click(
        page,
        '[data-test="shopping-cart-link"]'
    )

    wait_for_element(
        page,
        ".cart_item"
    )

    # Extract the product name
    product_name = extract_text(
        page,
        ".inventory_item_name"
    )

    print(f"Product in the cart: {product_name}")