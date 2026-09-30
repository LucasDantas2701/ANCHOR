from playwright.sync_api import Page


def wait_for_element(page: Page,selector: str,timeout: int = 10000) -> None:
    page.locator(selector).wait_for(state="visible",timeout=timeout)

def wait_for_url(page: Page, url: str, timeout: int = 10000) -> None:
    page.wait_for_url(url, timeout=timeout)

def wait(milliseconds: int) -> None:
    import time
    time.sleep(milliseconds / 1000)