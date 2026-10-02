"""
Saved automations from the terminal.

    python -m anchor.automations create register-employee --url eval/fixtures/registration.html \\
        --profile ollama-small "cadastre a Maria Silva no TI e salve"
    python -m anchor.automations run register-employee          # 1st time: learns; then: replays
    python -m anchor.automations run register-employee --relearn
    python -m anchor.automations list
    python -m anchor.automations show register-employee
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor.agent.__main__ import ProgressPlanner, to_url
from anchor.cli import apply_language, language_options, option
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.disambiguation import TerminalDisambiguator
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.i18n import t
from anchor.planner import ConfigError, get_profile
from anchor.planner.progress import Progress

from .model import Automation, AutomationError, AutomationStore
from .runner import run_automation


def cmd_create(store: AutomationStore, args) -> int:
    url = to_url(args.url)
    store.create(Automation(name=args.name, request=args.request, url=url, profile=args.profile,
                            browser_profile=args.browser_profile, prompt_language=args.prompt_language))
    print(t("auto.created", name=args.name, folder=store.folder(args.name)))
    return 0


def cmd_list(store: AutomationStore, args) -> int:
    names = store.names()
    if not names:
        print(t("auto.none"))
        return 0
    for name in names:
        automation, plan = store.load(name), store.load_plan(name)
        state = t("auto.state_approved", steps=len(plan.steps)) if plan else t("auto.state_new")
        print(f"  {name:28} {state:28} {automation.request[:60]}")
    return 0


def cmd_show(store: AutomationStore, args) -> int:
    automation, plan = store.load(args.name), store.load_plan(args.name)
    print(t("auto.show_request", request=automation.request))
    print(t("auto.show_url", url=automation.url))
    print(t("auto.show_profile", profile=automation.profile))
    if plan:
        print(t("auto.show_plan", approved=plan.approved.replace("T", " ")))
        for i, s in enumerate(plan.steps, 1):
            value = f' = "{s.value}"' if s.value is not None else ""
            print(f"    {i}. {s.action:12} {s.description}{value}")
    else:
        print(t("auto.state_new"))
    runs = store.runs(args.name)
    if runs:
        print(t("auto.show_runs", count=len(runs)))
        for r in runs[-5:]:
            print(f"    {r['id'][:15]}  {r['mode']:7} {r['status']:10} {r.get('seconds', 0):6.1f} s  {r['message'][:60]}")
    return 0


def cmd_run(store: AutomationStore, args) -> int:
    automation = store.load(args.name)
    progress = Progress("    ")

    def make_planner(auto: Automation):
        profile = get_profile(auto.profile)
        return ProgressPlanner(profile.planner(on_progress=progress.update,
                                               prompt_language=auto.prompt_language), progress)

    with sync_playwright() as p:
        if automation.browser_profile:
            context = p.chromium.launch_persistent_context(automation.browser_profile, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            context = p.chromium.launch(headless=False).new_context()
            page = context.new_page()
        page.goto(automation.url)
        executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=TerminalDisambiguator(),
                                  can_point=True, memory=ChoiceMemory(store.memory_path(args.name)))
        try:
            result, mode, run_id = run_automation(store, args.name, page, executor, make_planner,
                                                  relearn=args.relearn)
        except ConfigError as exc:
            print(t("cli.config_error", error=exc))
            context.close()
            return 1
        except KeyboardInterrupt:
            print("\n\n" + t("cli.interrupted"))
            context.close()
            return 130
        print("\n" + t("cli.result", status=result.status, message=result.message))
        print(t("cli.summary", steps=sum(r.status == "success" for r in result.records), calls=result.llm_calls,
                replans=result.replans, failures=result.failures, interventions=result.interventions,
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, seconds=result.seconds))
        try:
            input("\n" + t("cli.close_browser"))
        except KeyboardInterrupt:
            pass
        context.close()
    return 0 if result.ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m anchor.automations")
    option(ap, "--root", default="automations", help="folder of the saved automations")
    language_options(ap, prompt=False)
    sub = ap.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="creates an automation")
    create.add_argument("name", help="lowercase letters, digits, - and _")
    create.add_argument("request", help="what to do, in natural language")
    create.add_argument("--url", required=True, help="the site's link or the path of an .html file")
    create.add_argument("--profile", required=True, help="model profile in llm_profiles.json")
    create.add_argument("--browser-profile", help="folder of a persistent browser profile (systems with login)")
    create.add_argument("--prompt-language", choices=("pt", "en", "auto"), help="default: the model profile's")

    run = sub.add_parser("run", help="runs an automation (the first time, it learns the plan)")
    run.add_argument("name")
    run.add_argument("--relearn", action="store_true", help="plans again with the LLM, replacing the approved plan")

    sub.add_parser("list", help="lists the automations")
    show = sub.add_parser("show", help="shows an automation, its approved plan and its last runs")
    show.add_argument("name")

    args = ap.parse_args(argv)
    apply_language(args)
    store = AutomationStore(Path(args.root))
    commands = {"create": cmd_create, "run": cmd_run, "list": cmd_list, "show": cmd_show}
    try:
        return commands[args.command](store, args)
    except AutomationError as exc:
        print(t("auto.error", error=exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
