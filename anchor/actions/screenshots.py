from pathlib import Path

from playwright.sync_api import Page


def screenshot(page: Page,path: str,full_page: bool = False) -> str:

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page.screenshot(path=str(output_path),full_page=full_page)

    return str(output_path)