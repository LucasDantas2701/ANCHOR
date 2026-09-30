from anchor.engine.element_resolver import ElementResolver


def test_resolve_element(page):
    page.goto("https://www.saucedemo.com/")

    page.locator('[data-test="username"]').fill("standard_user")
    page.locator('[data-test="password"]').fill("secret_sauce")
    page.locator('[data-test="login-button"]').click()

    page.wait_for_url("**/inventory.html")

    print("URL:", page.url)
    print("BOTÕES:", page.locator("button").all_inner_texts())

    resolver = ElementResolver(page)

    print("ELEMENTOS INDEXADOS:", resolver.index())

    print("REGISTROS:")
    for record in resolver._records:
        if record["tag"] == "button":
            print(record)

    matches = resolver.query(
        "botão para adicionar a mochila ao carrinho",
        k=5,
        action="click",
    )

    for match in matches:
        print(match)

    assert matches