"""
Demo of the user's disambiguation, with a visible browser.

Run from the project root:

    python -m examples.disambiguation_demo

Step 1 is ambiguous (two similar "Add to cart" buttons): the terminal
asks which one, and the numbers appear in the browser window.
Step 2 is not found by the heuristic: type C and click the coffee
maker's heart in the browser window.

The choices are kept in memory/demo.json. Run it again: this time the
assistant asks nothing. Delete the file to start over. The steps are
user requests, in Portuguese, like the evaluation tasks.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator
from anchor.engine.memory import ChoiceMemory
from anchor.i18n import t

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
            print(t("demo.remembered", count=len(memory.entries), path=MEMORY))

        executor = ActionExecutor(
            page,
            disambiguator=TerminalDisambiguator(),
            can_point=True,
            memory=memory,
        )

        for action, description in STEPS:
            result = getattr(executor, action)(description)
            print("\n" + t("demo.result", result=result))

        input("\n" + t("cli.close_browser"))
        browser.close()


if __name__ == "__main__":
    main()
