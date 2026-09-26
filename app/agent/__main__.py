"""
Executa um pedido de ponta a ponta: plano, execução, replanejamento e fim.

    python -m app.agent --perfil ollama-pequeno --url eval/fixtures/cadastro.html "cadastre a Maria Silva no TI"
    python -m app.agent --perfil ollama-pequeno --url https://www.saucedemo.com --perfil-navegador profiles/user_001 \\
        --memoria memory/saucedemo.json "adicione a mochila ao carrinho e abra o carrinho"

O navegador fica visível: quando a heurística não tem certeza, o terminal
pergunta e os candidatos aparecem numerados na página.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.engine.action_executor import ActionExecutor
from app.engine.disambiguation import TerminalDisambiguator
from app.engine.element_resolver import ElementResolver
from app.engine.memory import ChoiceMemory
from app.planner import ConfigError, get_profile
from app.planner.progress import Progress

from .agent import Agent


def to_url(value: str) -> str:
    path = Path(value)
    return path.resolve().as_uri() if path.exists() else value


class ProgressPlanner:
    """Mostra o progresso do modelo em cada chamada ao planejador."""

    def __init__(self, planner, progress: Progress):
        self.planner, self.progress = planner, progress

    def plan(self, *args, **kwargs):
        with self.progress:
            return self.planner.plan(*args, **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.agent")
    ap.add_argument("pedido")
    ap.add_argument("--perfil", required=True, help="perfil do modelo em llm_profiles.json")
    ap.add_argument("--url", required=True, help="link do site ou caminho de um arquivo .html")
    ap.add_argument("--memoria", default="memory/agente.json", help="arquivo da memória das escolhas")
    ap.add_argument("--perfil-navegador", help="pasta de um perfil persistente (sistemas com login)")
    ap.add_argument("--max-tentativas", type=int, default=3)
    args = ap.parse_args()

    try:
        profile = get_profile(args.perfil)
        progress = Progress("    ")
        planner = ProgressPlanner(profile.planner(on_progress=progress.update), progress)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}")
        return 1

    with sync_playwright() as p:
        if args.perfil_navegador:
            context = p.chromium.launch_persistent_context(args.perfil_navegador, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            context = p.chromium.launch(headless=False).new_context()
            page = context.new_page()
        page.goto(to_url(args.url))

        executor = ActionExecutor(
            page,
            resolver=ElementResolver(page),
            disambiguator=TerminalDisambiguator(),
            can_point=True,
            memory=ChoiceMemory(args.memoria),
        )
        result = Agent(page, planner, executor, max_failures=args.max_tentativas).run(args.pedido)

        print(f"\nResultado: {result.status} — {result.message}")
        print(f"Passos executados: {sum(r.status == 'success' for r in result.records)} | "
              f"chamadas ao modelo: {result.llm_calls} | replanejamentos: {result.replans} | "
              f"falhas: {result.failures} | intervenções do usuário: {result.interventions} | "
              f"tokens: {result.tokens_in}+{result.tokens_out} | tempo: {result.seconds} s")
        input("\nEnter para fechar o navegador...")
        context.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
