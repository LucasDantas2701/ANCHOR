"""
Preparation steps for each site before its cases (login, navigation...).
Referenced by the "setup" field of the files in eval/cases/.
"""

from playwright.sync_api import Page


def saucedemo_login(page: Page) -> None:
    page.locator('[data-test="username"]').fill("standard_user")
    page.locator('[data-test="password"]').fill("secret_sauce")
    page.locator('[data-test="login-button"]').click()
    page.locator(".inventory_list").wait_for(state="visible")


SETUPS = {
    "saucedemo_login": saucedemo_login,
}
