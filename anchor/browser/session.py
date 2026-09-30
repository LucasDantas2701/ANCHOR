from playwright.sync_api import Page


def is_logged_in(page: Page,logged_in_selector: str) -> bool:

    try:
        page.locator(logged_in_selector).wait_for(
            state="visible",
            timeout=5000
        )
        return True

    except:
        return False


def wait_for_login(
    page: Page,
    logged_in_selector: str,
    timeout: int = 120000
) -> None:
    
    print("Usuário não está logado.")
    print("Faça o login no navegador.")

    page.locator(logged_in_selector).wait_for(
        state="visible",
        timeout=timeout
    )

    print("Login detectado!")