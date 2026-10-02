"""
Saved automations from the terminal.

    python -m anchor.automations create register-employee --url eval/fixtures/registration.html \\
        --profile ollama-small "cadastre a Maria Silva no TI e salve"
    python -m anchor.automations run register-employee          # 1st time: learns; then: replays
    python -m anchor.automations run register-employee --relearn
    python -m anchor.automations run register-employee --no-heal  # stop instead of healing

    With parameters, in braces in the request:
    python -m anchor.automations create register --url ... --profile ollama-small "cadastre {nome}, CPF {cpf}, no TI e salve"
    python -m anchor.automations run register --param nome="Maria Silva" --param cpf=123.456.789-00
    python -m anchor.automations run register --csv employees.csv          # one run per row
    python -m anchor.automations list
    python -m anchor.automations show register-employee
    python -m anchor.automations recoveries register-employee   # how it recovered when the site changed
    python -m anchor.automations undo register-employee 2       # undo recovery #2
    python -m anchor.automations notes register-employee        # the notes sent to the planner
    python -m anchor.automations notes register-employee --add "o botão Salvar fica no fim da página"
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
from .params import ParameterError, parse_assignments, read_rows
from .runner import run_automation, undo_recovery


def cmd_create(store: AutomationStore, args) -> int:
    url = to_url(args.url)
    store.create(Automation(name=args.name, request=args.request, url=url, profile=args.profile,
                            browser_profile=args.browser_profile, prompt_language=args.prompt_language))
    created = store.load(args.name)
    print(t("auto.created", name=args.name, folder=store.folder(args.name)))
    if created.parameters:
        print(t("auto.parameters", names=", ".join(created.parameters)))
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
    if automation.parameters:
        print(t("auto.parameters", names=", ".join(automation.parameters)))
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
    try:
        if args.csv:
            rows = read_rows(args.csv)
            if not rows:
                raise ParameterError(t("auto.csv_empty", path=args.csv))
        else:
            rows = [parse_assignments(args.param)]
    except (ParameterError, OSError) as exc:
        print(t("auto.error", error=exc))
        return 1
    progress = Progress("    ")

    def make_planner(auto: Automation):
        profile = get_profile(auto.profile)
        return ProgressPlanner(profile.planner(on_progress=progress.update,
                                               prompt_language=auto.prompt_language), progress)

    outcomes = []
    last_run = ""
    with sync_playwright() as p:
        if automation.browser_profile:
            context = p.chromium.launch_persistent_context(automation.browser_profile, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            context = p.chromium.launch(headless=False).new_context()
            page = context.new_page()
        executor = ActionExecutor(page, resolver=ElementResolver(page), disambiguator=TerminalDisambiguator(),
                                  can_point=True, memory=ChoiceMemory(store.memory_path(args.name)))
        for number, values in enumerate(rows, 1):
            if len(rows) > 1:
                print("\n" + t("auto.row", number=number, total=len(rows)))
            page.goto(automation.url)
            try:
                result, mode, run_id = run_automation(store, args.name, page, executor, make_planner,
                                                      relearn=args.relearn and number == 1,
                                                      heal=not args.no_heal, params=values)
            except (ConfigError, AutomationError) as exc:
                print(t("auto.error", error=exc))
                if len(rows) == 1:
                    context.close()
                    return 1
                outcomes.append((number, "error", str(exc)))
                continue
            except KeyboardInterrupt:
                print("\n\n" + t("cli.interrupted"))
                context.close()
                return 130
            print("\n" + t("cli.result", status=result.status, message=result.message))
            print(t("cli.summary", steps=sum(r.status == "success" for r in result.records), calls=result.llm_calls,
                    replans=result.replans, failures=result.failures, interventions=result.interventions,
                    tokens_in=result.tokens_in, tokens_out=result.tokens_out, seconds=result.seconds))
            outcomes.append((number, result.status, result.message))
            last_run = run_id
        failed = [o for o in outcomes if o[1] != "success"]
        if failed and sys.stdin.isatty():
            ask_for_note(store, args.name, last_run if len(rows) == 1 else "")
        if len(rows) > 1:
            done = sum(status == "success" for _, status, _ in outcomes)
            print("\n" + t("auto.csv_summary", done=done, total=len(rows)))
            for number, status, message in outcomes:
                if status != "success":
                    print(f"    {number:4}  {status:10} {message[:80]}")
        try:
            input("\n" + t("cli.close_browser"))
        except KeyboardInterrupt:
            pass
        context.close()
    return 0 if all(status == "success" for _, status, _ in outcomes) else 1


def ask_for_note(store: AutomationStore, name: str, run_id: str = "") -> None:
    """After a run that did not work, the user may leave a note for the planner."""
    try:
        text = input("\n" + t("auto.ask_note") + " ").strip()
    except (KeyboardInterrupt, EOFError):
        return
    if text:
        note = store.add_note(name, text, run=run_id)
        print(t("auto.note_saved", number=note["number"]))


def cmd_notes(store: AutomationStore, args) -> int:
    store.load(args.name)
    if args.add:
        note = store.add_note(args.name, args.add)
        print(t("auto.note_saved", number=note["number"]))
        return 0
    if args.remove is not None:
        if not store.remove_note(args.name, args.remove):
            print(t("auto.error", error=t("auto.no_note", number=args.remove)))
            return 1
        print(t("auto.note_removed", number=args.remove))
        return 0
    notes = store.notes(args.name)
    if not notes:
        print(t("auto.no_notes"))
        return 0
    recent = {n["number"] for n in notes[-store.NOTES_SENT:]}
    for n in notes:
        sent = "" if n["number"] in recent else t("auto.note_not_sent")
        print(f"  #{n['number']} {n['date'].replace('T', ' ')}  {n['text']}{sent}")
    return 0


def _confidence(items: list) -> str:
    scores = [i["score"] for i in items if i.get("score") is not None]
    by = sorted({i["resolved_by"] for i in items if i.get("resolved_by")})
    return (f"{min(scores):.2f}" if scores else "—") + (f" ({', '.join(by)})" if by else "")


def _step_text(step) -> str:
    if not step:
        return "—"
    value = f' = "{step["value"]}"' if step.get("value") is not None else ""
    return f'{step["action"]} {step["description"]}{value}'


def cmd_recoveries(store: AutomationStore, args) -> int:
    store.load(args.name)
    records = store.recoveries(args.name)
    if not records:
        print(t("auto.no_recoveries"))
        return 0
    for r in records:
        undone = t("auto.undone_mark") if r["undone"] else ""
        date = r["date"].replace("T", " ")
        if r["method"] == "replan":
            print(t("auto.recovery_replan", number=r["number"], date=date, undone=undone,
                    failed=_step_text(r.get("failed_step")), reason=r.get("reason", ""),
                    replaced="; ".join(_step_text(s) for s in r.get("replaced_by", [])) or "—",
                    effect=t("auto.yes") if r.get("effect_confirmed") else t("auto.no"),
                    confidence=_confidence(r.get("confidence", []))))
        else:
            print(t("auto.recovery_user", number=r["number"], date=date, undone=undone,
                    description=r["step"]["description"]))
    return 0


def cmd_undo(store: AutomationStore, args) -> int:
    store.load(args.name)
    try:
        record = undo_recovery(store, args.name, args.number, memory=ChoiceMemory(store.memory_path(args.name)))
    except ValueError as exc:
        print(t("auto.error", error=exc))
        return 1
    if record["method"] == "replan":
        print(t("auto.undo_replan", number=record["number"]))
    else:
        print(t("auto.undo_user", number=record["number"], description=record["step"]["description"]))
    return 0


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
    run.add_argument("--no-heal", action="store_true",
                     help="if a saved step stops working, stop instead of recovering with the LLM")
    values = run.add_mutually_exclusive_group()
    values.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                        help="the value of a parameter for this run (repeat for each one)")
    values.add_argument("--csv", metavar="FILE",
                        help="runs once per row of a CSV file, whose columns are the parameters")

    sub.add_parser("list", help="lists the automations")
    show = sub.add_parser("show", help="shows an automation, its approved plan and its last runs")
    show.add_argument("name")
    recoveries = sub.add_parser("recoveries", help="lists how the automation recovered when the site changed")
    recoveries.add_argument("name")
    undo = sub.add_parser("undo", help="undoes a recovery (by the number shown by 'recoveries')")
    undo.add_argument("name")
    undo.add_argument("number", type=int)
    notes = sub.add_parser("notes", help="lists, adds or removes the notes sent to the planner")
    notes.add_argument("name")
    notes_action = notes.add_mutually_exclusive_group()
    notes_action.add_argument("--add", metavar="TEXT", help="adds a note")
    notes_action.add_argument("--remove", type=int, metavar="NUMBER", help="removes a note")

    args = ap.parse_args(argv)
    apply_language(args)
    store = AutomationStore(Path(args.root))
    commands = {"create": cmd_create, "run": cmd_run, "list": cmd_list, "show": cmd_show,
                "recoveries": cmd_recoveries, "undo": cmd_undo, "notes": cmd_notes}
    try:
        return commands[args.command](store, args)
    except AutomationError as exc:
        print(t("auto.error", error=exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
