from playwright.sync_api import Page


def extract_text(page: Page, selector: str) -> str:
    return page.locator(selector).inner_text()

def extract_attribute(page: Page, selector: str, attribute: str) -> str | None:
    return page.locator(selector).get_attribute(attribute)

def extract_value(page: Page, selector: str) -> str:
    return page.locator(selector).input_value()

def element_exists(page: Page, selector: str) -> bool:
    return page.locator(selector).count() > 0