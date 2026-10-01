"""
Demonstração do desempate pelo usuário, com o navegador visível.

Rodar na raiz do projeto:

    python -m examples.desempate

Passo 1 é ambíguo (dois botões "Add to cart" parecidos): o terminal
pergunta qual deles, e os números aparecem na janela do navegador.
Passo 2 não é encontrado pela heurística: digite C e clique no
coração da cafeteira na janela do navegador.

As escolhas ficam em memory/demo.json. Rode de novo: desta vez o
assistente não pergunta nada. Apague o arquivo para recomeçar.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator
from anchor.engine.memory import ChoiceMemory

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "eval" / "fixtures" / "store.html"
MEMORY = ROOT / "memory" / "demo.json"

STEPS = [
    ("click", "adicionar ao carrinho"),
    ("click", "marcar a cafeteira como favorita"),
]


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(PAGE.as_uri())

        memory = ChoiceMemory(MEMORY)
        if memory.entries:
            print(f"Tenho {len(memory.entries)} escolha(s) memorizada(s) em {MEMORY}.")
            print("Apague o arquivo para o assistente perguntar de novo.")

        executor = ActionExecutor(
            page,
            disambiguator=TerminalDisambiguator(),
            can_point=True,
            memory=memory,
        )

        for action, description in STEPS:
            result = getattr(executor, action)(description)
            print(f"\nResultado: {result}")

        input("\nEnter para fechar o navegador...")
        browser.close()


if __name__ == "__main__":
    main()
