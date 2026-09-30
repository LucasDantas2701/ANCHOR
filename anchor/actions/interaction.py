from playwright.sync_api import Page


def click(page: Page, selector: str) -> None:
    page.locator(selector).click()

def type_text(page: Page, selector: str, text: str) -> None:
    page.locator(selector).fill(text)

def press(page: Page, selector: str, key: str) -> None:
    page.locator(selector).press(key)

def select_option(page: Page, selector: str, value: str) -> None:
    page.locator(selector).select_option(value)

def check(page: Page, selector: str) -> None:
    page.locator(selector).check()

def uncheck(page: Page, selector: str) -> None:
    page.locator(selector).uncheck()

def hover(page: Page, selector: str) -> None:
    page.locator(selector).hover()