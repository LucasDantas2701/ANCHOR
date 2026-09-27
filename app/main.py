"""
Exemplo de ponta a ponta no SauceDemo, com o motor semântico.

    python -m app.main

1. Abre o navegador com um perfil persistente (profiles/user_001).
2. Se não houver sessão, espera o usuário fazer o login manualmente
   (usuário: standard_user, senha: secret_sauce). A senha nunca passa
   pelo sistema.
3. Executa passos descritos em linguagem natural. Quando a heurística
   não tem certeza, pergunta no terminal; as escolhas ficam em
   memory/saucedemo.json e não são perguntadas de novo.

Aqui o plano (a lista de passos) é fixo, para demonstrar o motor sem LLM.
Para um pedido em texto, com o plano gerado pelo LLM, use o agente:
python -m app.agent --perfil <perfil> --url <link> "<pedido>"

Versão antiga, com seletores fixos, para comparação:
app/automation/saucedemo.py
"""

from pathlib import Path

from app.browser.browser import close_browser, start_browser
from app.browser.session import is_logged_in, wait_for_login
from app.engine.action_executor import ActionExecutor
from app.engine.disambiguation import TerminalDisambiguator
from app.engine.element_resolver import ElementResolver
from app.engine.memory import ChoiceMemory

PROFILE_PATH = "./profiles/user_001"
URL = "https://www.saucedemo.com/"
LOGGED_IN_SELECTOR = ".inventory_list"
MEMORY = Path("memory") / "saucedemo.json"

# Vocabulário específico do site (fica fora do dicionário genérico).
VOCAB = {
    "mochila": "backpack",
    "lanterna": "light",
    "bicicleta": "bike",
    "camiseta": "shirt",
    "jaqueta": "jacket",
}

PLAN = [
    ("click", "adicionar a mochila ao carrinho", {}),
    ("click", "adicionar a lanterna de bicicleta ao carrinho", {}),
    ("click", "abrir o carrinho", {}),
]


def run(page) -> list:
    executor = ActionExecutor(
        page,
        resolver=ElementResolver(page, synonyms=VOCAB),
        disambiguator=TerminalDisambiguator(),
        can_point=True,
        memory=ChoiceMemory(MEMORY),
    )

    results = []
    for action, description, kwargs in PLAN:
        result = getattr(executor, action)(description, **kwargs)
        print(f"- {description}: {result.status} (por: {result.resolved_by})")
        results.append(result)
        if not result:
            print("  Passo não concluído; encerrando.")
            break
    return results


def main():
    playwright, context = start_browser(PROFILE_PATH)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(URL)

    if is_logged_in(page, LOGGED_IN_SELECTOR):
        print("Usuário já está logado.")
    else:
        wait_for_login(page, LOGGED_IN_SELECTOR)

    print("Iniciando automação...")
    run(page)

    input("Pressione ENTER para encerrar...")
    close_browser(playwright, context)


if __name__ == "__main__":
    main()
