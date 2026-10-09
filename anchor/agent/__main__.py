"""
Runs a request end to end: plan, execution, replanning and end.

    python -m anchor.agent --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria Silva no TI"
    python -m anchor.agent --profile ollama-small --url https://www.saucedemo.com --browser-profile profiles/user_001 \\
        --memory memory/saucedemo.json "adicione a mochila ao carrinho e abra o carrinho"

The browser stays visible: when the heuristic is not sure, the terminal asks
and the candidates appear numbered on the page. The old Portuguese options
(--perfil, --memoria, --perfil-navegador, --max-tentativas) still work.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.agent.login import TerminalLoginWaiter
from anchor.cli import apply_language, language_options, option, require
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.engine.sensitive import TerminalConfirmer
from anchor.i18n import t
from anchor.planner import ConfigError, get_profile
from anchor.planner.progress import Progress

from .agent import Agent


def to_url(value: str) -> str:
    path = Path(value)
    return path.resolve().as_uri() if path.exists() else value


class ProgressPlanner:
    """Shows the model's progress on each call to the planner."""

    def __init__(self, planner, progress: Progress):
        self.planner, self.progress = planner, progress

    @property
    def language(self) -> str:
        # The agent writes the history in the planner's language: pass it through.
        return self.planner.language

    def language_for(self, request: str) -> str:
        return self.planner.language_for(request)

    def plan(self, *args, **kwargs):
        with self.progress:
            return self.planner.plan(*args, **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m anchor.agent")
    ap.add_argument("request", help="what to do, in natural language")
    option(ap, "--profile", "--perfil", help="model profile in llm_profiles.json")
    option(ap, "--url", help="the site's link or the path of an .html file")
    option(ap, "--memory", "--memoria", default="memory/agent.json", help="choice memory file")
    option(ap, "--browser-profile", "--perfil-navegador", help="folder of a persistent profile (systems with login)")
    option(ap, "--max-attempts", "--max-tentativas", type=int, default=3, help="failures before cancelling")
    option(ap, "--vision", action="store_true",
           help="when the other checks doubt a step, asks the model about a screenshot (slower)")
    option(ap, "--allow-sensitive", action="store_true",
           help="does not ask before sensitive actions (delete, save, send, pay, download, upload)")
    option(ap, "--output-dir", "--pasta-saida", default="output",
           help="where extracted tables and lists are saved as CSV")
    language_options(ap)
    args = ap.parse_args()
    require(ap, args, "--profile", "--url")
    apply_language(args)

    try:
        profile = get_profile(args.profile)
        progress = Progress("    ")
        planner = ProgressPlanner(profile.planner(on_progress=progress.update,
                                                  prompt_language=args.prompt_language), progress)
    except ConfigError as exc:
        print(t("cli.config_error", error=exc))
        return 1

    with sync_playwright() as p:
        if args.browser_profile:
            context = p.chromium.launch_persistent_context(args.browser_profile, headless=False)
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
            memory=ChoiceMemory(args.memory),
            confirmer=None if args.allow_sensitive else TerminalConfirmer(),
        )
        vision = None
        if args.vision:
            from .vision import VisionChecker
            vision = VisionChecker(profile.client(), profile.model)
        try:
            result = Agent(page, planner, executor, max_failures=args.max_attempts, vision=vision,
                           output_dir=args.output_dir, login=TerminalLoginWaiter()).run(args.request)
        except KeyboardInterrupt:
            print("\n\n" + t("cli.interrupted"))
            context.close()
            return 130

        print("\n" + t("cli.result", status=result.status, message=result.message))
        print(t("cli.summary", steps=sum(r.status == "success" for r in result.records), calls=result.llm_calls,
                replans=result.replans, failures=result.failures, interventions=result.interventions,
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, seconds=result.seconds,
                waited=result.user_wait_seconds))
        try:
            input("\n" + t("cli.close_browser"))
        except KeyboardInterrupt:
            pass
        context.close()
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
