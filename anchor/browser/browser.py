from playwright.sync_api import BrowserContext, Playwright, sync_playwright


def start_browser(profile_path: str) -> tuple[Playwright, BrowserContext]:
    playwright = sync_playwright().start()

    context = playwright.chromium.launch_persistent_context(
    user_data_dir=profile_path,
    headless=False,
    args=[
        "--disable-notifications"
    ]
)

    return playwright, context


def close_browser(
    playwright: Playwright,
    context: BrowserContext
) -> None:
    context.close()
    playwright.stop()