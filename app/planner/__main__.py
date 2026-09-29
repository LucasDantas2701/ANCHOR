"""
Gera (e opcionalmente executa) um plano a partir de um pedido e um link.

    python -m app.planner --perfil ollama-pequeno --url https://www.saucedemo.com "adicione a mochila ao carrinho"
    python -m app.planner --perfil openai --url eval/fixtures/cadastro.html "cadastre a Maria no RH" --executar
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.engine.action_executor import ActionExecutor
from app.engine.disambiguation import TerminalDisambiguator
from app.engine.element_resolver import ElementResolver

from .config import ConfigError, get_profile
from .execute import run_plan
from .page_summary import page_elements
from .plan import PlanError
from .progress import Progress


def to_url(value: str) -> str:
    path = Path(value)
    return path.resolve().as_uri() if path.exists() else value


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.planner")
    ap.add_argument("pedido")
    ap.add_argument("--perfil", required=True, help="nome do perfil em llm_profiles.json")
    ap.add_argument("--url", required=True, help="link do site ou caminho de um arquivo .html")
    ap.add_argument("--executar", action="store_true", help="executa o plano no navegador")
    ap.add_argument("--sem-pagina", action="store_true", help="não envia a lista de elementos ao modelo")
    args = ap.parse_args()

    try:
        profile = get_profile(args.perfil)
        progress = Progress("  ")
        planner = profile.planner(on_progress=progress.update)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.executar)
        page = browser.new_page()
        page.goto(to_url(args.url))
        resolver = ElementResolver(page)
        elements = None if args.sem_pagina else page_elements(resolver, request=args.pedido)

        print(f"Gerando o plano com {profile.model} (na primeira vez, inclui carregar o modelo)...")
        try:
            with progress:
                plan = planner.plan(args.pedido, page.url, elements)
        except PlanError as exc:
            print(f"O modelo não gerou um plano válido: {exc}")
            return 1
        except Exception as exc:  # conexão, autenticação, modelo inexistente...
            print(f"Falha ao chamar o modelo: {type(exc).__name__}: {exc}")
            return 1

        print(f"\nPlano ({len(plan.steps)} passos, {plan.latency_s}s, "
              f"{plan.tokens_in}+{plan.tokens_out} tokens, {plan.attempts} tentativa(s)):")
        for g in plan.goals:
            print(f"  meta {g.id}: {g.description}" + ("  (conclusiva)" if g.conclusive else ""))
        for i, s in enumerate(plan.steps, 1):
            value = f' = "{s.value}"' if s.value is not None else ""
            goal = f"  [{s.goal}]" if s.goal else ""
            expect = f'  → espera "{s.expect}"' if s.expect else ""
            print(f"  {i}. {s.action:12} {s.description}{value}{goal}{expect}")

        if args.executar and plan.steps:
            executor = ActionExecutor(page, resolver=resolver, disambiguator=TerminalDisambiguator(), can_point=True)
            print()
            for step, result in run_plan(executor, plan):
                print(f"- {step.description}: {result.status} (por: {result.resolved_by})")
            input("\nEnter para fechar o navegador...")
        browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
        sys.exit(130)
