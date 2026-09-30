from pathlib import Path

from playwright.sync_api import Page


def download_file(page: Page,selector: str,path: str) -> str:

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with page.expect_download() as download_info:
        page.locator(selector).click()

    download = download_info.value
    download.save_as(str(output_path))

    return str(output_path)