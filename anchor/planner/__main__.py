"""
Generates (and optionally runs) a plan from a request and a link.

    python -m anchor.planner --profile ollama-small --url https://www.saucedemo.com "adicione a mochila ao carrinho"
    python -m anchor.planner --profile ollama-small --url eval/fixtures/registration.html "cadastre a Maria no RH" --run

The old Portuguese options (--perfil, --executar, --sem-pagina) still work.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.cli import apply_language, language_options, option, require
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.sensitive import TerminalConfirmer
from anchor.i18n import t

from .config import ConfigError, get_profile
from .execute import run_plan
from .page_summary import page_elements
from .plan import PlanError
from .progress import Progress


def to_url(value: str) -> str:
    path = Path(value)
    return path.resolve().as_uri() if path.exists() else value


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m anchor.planner")
    ap.add_argument("request", help="what to do, in natural language")
    option(ap, "--profile", "--perfil", help="profile name in llm_profiles.json")
    option(ap, "--url", help="the site's link or the path of an .html file")
    option(ap, "--run", "--executar", action="store_true", help="runs the plan in the browser")
    option(ap, "--no-page", "--sem-pagina", action="store_true", help="does not send the list of elements to the model")
    option(ap, "--allow-sensitive", action="store_true",
           help="with --run: does not ask before sensitive actions (delete, save, send, pay, download, upload)")
    language_options(ap)
    args = ap.parse_args()
    require(ap, args, "--profile", "--url")
    apply_language(args)

    from anchor.agent.login import request_has_password
    if request_has_password(args.request):
        print(t("cli.result", status="failed", message=t("end.password_in_request")))
        return 1

    try:
        profile = get_profile(args.profile)
        progress = Progress("  ")
        planner = profile.planner(on_progress=progress.update, prompt_language=args.prompt_language)
    except ConfigError as exc:
        print(t("cli.config_error", error=exc))
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.run)
        page = browser.new_page()
        page.goto(to_url(args.url))
        resolver = ElementResolver(page)
        elements = None if args.no_page else page_elements(resolver, request=args.request, language=planner.language_for(args.request))

        print(t("planner_cli.generating", model=profile.model))
        try:
            with progress:
                plan = planner.plan(args.request, page.url, elements)
        except PlanError as exc:
            print(t("planner_cli.invalid", error=exc))
            return 1
        except Exception as exc:  # connection, authentication, missing model...
            print(t("planner_cli.call_failed", kind=type(exc).__name__, error=exc))
            return 1

        print("\n" + t("planner_cli.header", steps=len(plan.steps), seconds=plan.latency_s,
                       tokens_in=plan.tokens_in, tokens_out=plan.tokens_out, attempts=plan.attempts))
        for g in plan.goals:
            print(t("planner_cli.goal", id=g.id, description=g.description)
                  + (t("planner_cli.conclusive") if g.conclusive else ""))
        for i, s in enumerate(plan.steps, 1):
            value = f' = "{s.value}"' if s.value is not None else ""
            goal = f"  [{s.goal}]" if s.goal else ""
            expect = t("planner_cli.expects", text=s.expect) if s.expect else ""
            print(f"  {i}. {s.action:12} {s.description}{value}{goal}{expect}")

        if args.run and plan.steps:
            executor = ActionExecutor(page, resolver=resolver, disambiguator=TerminalDisambiguator(), can_point=True,
                                      confirmer=None if args.allow_sensitive else TerminalConfirmer())
            executor.refuse_passwords = True    # a password field is never typed into
            print()
            for step, result in run_plan(executor, plan):
                print(t("demo.step", description=step.description, status=result.status, by=result.resolved_by))
            input("\n" + t("cli.close_browser"))
        browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n" + t("cli.interrupted"))
        sys.exit(130)
