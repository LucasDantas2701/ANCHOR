from playwright.sync_api import Page


def navigate(page: Page, url: str) -> None:
    page.goto(url)

def go_back(page: Page) -> None:
    page.go_back()


def go_forward(page: Page) -> None:
    page.go_forward()


def reload(page: Page) -> None:
    page.reload()