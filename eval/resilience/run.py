"""
Runs the resilience benchmark: the traditional script, the LLM in control and ANCHOR, on the
altered pages of eval/plans/resilience_tasks.json (build them with python -m eval.resilience.build).

    python -m eval.resilience.run --executors script
    python -m eval.resilience.run --executors anchor --profiles ollama-small --language pt
    python -m eval.resilience.run --executors llm --profiles ollama-medium --language en
    python -m eval.resilience.report eval/results/resilience_*.json      # the tables, from the parts

Each part saves its own results, so the benchmark can run in parts (an executor, a model and a
language at a time) and be put together by the report.

    script  replays the fixed selectors recorded on L0 (no model: --profiles is ignored)
    llm     the model chooses every action and element, with no protection (one run per task)
    anchor  a saved automation whose approved plan is the reference plan (the same plan the script
            was recorded from), run twice on each altered page, with no user: the 1st run measures
            the recovery (with healing by the model), the 2nd the reuse (the corrected plan again,
            which should need no model)

Every run is judged the same way: the task's checks (success), a success claimed with failing
checks (false success), elements acted on outside the allowed ones (unrequested), attacks that
worked and attempts (level 5), model calls and time.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from anchor import __version__
from anchor.cli import option
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.memory import ChoiceMemory
from anchor.planner import ConfigError, Step, get_profile
from eval.plan_run import INSTRUMENT, attack_attempts
from eval.resilience.executors import run_llm, run_script

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "plans" / "resilience_tasks.json"
SCRIPTS = ROOT / "plans" / "resilience_scripts.json"
EXECUTORS = ("script", "llm", "anchor")


@dataclass
class Row:
    executor: str
    profile: str
    task: str
    base_task: str
    level: int
    language: str
    run: int                  # anchor: 1 = recovery, 2 = reuse; others: 1
    success: bool
    claimed_success: bool
    false_success: bool
    unrequested: int
    attacked: bool
    attack_attempts: int
    llm_calls: int
    healed: bool
    seconds: float
    error: str
    steps: str = ""           # JSON: [action, description, value, status, how it was resolved, element acted on]


def judge(page, task: dict, claimed: bool, steps: list, executor: str, profile: str, run: int,
          llm_calls: int, seconds: float, error: str = "", healed: bool = False, log: list | None = None) -> Row:
    checks = all(page.evaluate(f"() => Boolean({c})") for c in task["checks"])
    unrequested = page.evaluate("(allowed) => window.__unrequested(allowed)", task["allowed"])
    attacks = [a for a in task.get("attacks", []) if page.evaluate(f"() => Boolean({a})")]
    tried = attack_attempts(task, steps)
    return Row(executor, profile, task["id"], task["base_task"], task["level"], task.get("language", "pt"), run,
               success=checks, claimed_success=claimed, false_success=claimed and not checks,
               unrequested=len(unrequested), attacked=bool(attacks), attack_attempts=len(tried),
               llm_calls=llm_calls, healed=healed, seconds=round(seconds, 2), error=error[:200],
               steps=json.dumps(log or [], ensure_ascii=False))


def fresh_page(browser, task: dict):
    page = browser.new_page()
    page.add_init_script(INSTRUMENT)
    page.set_default_timeout(3000)
    page.goto((ROOT / "fixtures" / task["fixture"]).as_uri())
    return page


def run_anchor(browser, task: dict, make_planner, profile: str, folder: Path) -> list[Row]:
    """The reference plan as a saved automation, run twice on the altered page."""
    from anchor.automations import Automation, AutomationStore, run_automation
    from anchor.automations.model import ApprovedPlan

    store = AutomationStore(folder / task["id"].replace("@", "_"))
    name = "task"
    store.create(Automation(name=name, request=task["request"], url="x", profile=profile))
    store.save_plan(name, ApprovedPlan(steps=[Step(a, d, v) for a, d, v in task["reference"]], goals=[]))
    rows = []
    for run in (1, 2):
        page = fresh_page(browser, task)
        executor = ActionExecutor(page, resolver=ElementResolver(page), memory=ChoiceMemory(store.memory_path(name)))
        try:
            result, _, _ = run_automation(store, name, page, executor, make_planner, report=None, heal=True)
            healed = bool(store.runs(name)[-1].get("healed"))
            steps = [r.step for r in result.records]
            log = [[r.step.action, r.step.description, r.step.value, r.status, r.resolved_by, r.element]
                   for r in result.records]
            rows.append(judge(page, task, result.ok, steps, "anchor", profile, run, result.llm_calls, result.seconds,
                              "" if result.ok else result.message, healed, log))
        except Exception as exc:                      # an error of the run itself, recorded as a failure
            rows.append(judge(page, task, False, [], "anchor", profile, run, 0, 0.0, f"{type(exc).__name__}: {exc}"))
        page.close()
    return rows


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "no-git"


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.resilience.run")
    option(ap, "--executors", nargs="+", choices=EXECUTORS, default=list(EXECUTORS), help="which executors to run")
    option(ap, "--profiles", nargs="*", default=[], help="model profiles (for llm and anchor)")
    option(ap, "--language", choices=("pt", "en"), help="only the tasks in this language (default: both)")
    option(ap, "--levels", nargs="+", type=int, default=[1, 2, 3, 4, 5], help="perturbation levels (default: 1 to 5)")
    option(ap, "--task", help="only one base task (e.g. p-reg-01)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="shows the error and the steps (with the element acted on) of the runs that need a look")
    args = ap.parse_args()

    tasks = [t for t in json.loads(TASKS.read_text(encoding="utf-8"))["tasks"] if t["level"] in args.levels]
    if args.language:
        tasks = [t for t in tasks if t.get("language", "pt") == args.language]
    if args.task:
        tasks = [t for t in tasks if t["base_task"] == args.task]
    scripts = json.loads(SCRIPTS.read_text(encoding="utf-8"))["scripts"]
    needs_model = [e for e in args.executors if e != "script"]
    if needs_model and not args.profiles:
        ap.error(f"{', '.join(needs_model)} need --profiles")

    rows: list[Row] = []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        runs = [("script", None)] if "script" in args.executors else []
        runs += [(e, name) for e in ("llm", "anchor") if e in args.executors for name in args.profiles]
        for executor, profile_name in runs:
            print(f"\n=== {executor}" + (f" ({profile_name})" if profile_name else ""))
            if profile_name:
                try:
                    profile = get_profile(profile_name)
                except ConfigError as exc:
                    print(f"[{profile_name}] {exc}")
                    return 1
                client = profile.client()
            for task in tasks:
                if executor == "script":
                    page = fresh_page(browser, task)
                    o = run_script(page, scripts[task["base_task"]])
                    new = [judge(page, task, o.claimed_success, [Step(a, s, v) for a, s, v, _ in o.steps],
                                 "script", "", 1, 0, o.seconds, o.error, log=o.steps)]
                    page.close()
                elif executor == "llm":
                    page = fresh_page(browser, task)
                    o = run_llm(page, task["request"], client, profile.model)
                    new = [judge(page, task, o.claimed_success, [Step(a, d, v) for a, d, v, _ in o.steps],
                                 "llm", profile_name, 1, o.llm_calls, o.seconds, o.error, log=o.steps)]
                    page.close()
                else:
                    new = run_anchor(browser, task, lambda _a, pr=profile: pr.planner(), profile_name,
                                     Path(tmp) / profile_name)
                rows += new
                for r in new:
                    mark = ("FALSE" if r.false_success else "OK " if r.success else "---")
                    extra = (f" run {r.run}" if executor == "anchor" else "") + (" healed" if r.healed else "")
                    print(f"[{mark}] {r.task:16}{extra} {r.seconds:6.1f}s  LLM {r.llm_calls}"
                          + ("  ATTACKED" if r.attacked else "") + (f"  attempts {r.attack_attempts}" if r.attack_attempts else "")
                          + (f"  {r.error[:70]}" if args.verbose and r.error else ""))
                    if args.verbose and (not r.success or r.attacked or r.false_success or r.healed):
                        for s in json.loads(r.steps):
                            how = f" [{s[4]}]" if len(s) > 4 and s[4] else ""
                            acted = f" → {s[5]}" if len(s) > 5 and s[5] else ""
                            value = f' = "{s[2]}"' if s[2] is not None else ""
                            print(f"        {s[3]:9} {s[0]:7} {s[1][:60]}{value}{how}{acted}")
        browser.close()

    if not rows:
        print("No run.")
        return 1
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    tag = "-".join(args.executors) + ("_" + "-".join(args.profiles) if args.profiles else "") + \
          (f"_{args.language}" if args.language else "")
    stem = f"resilience_{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}_{tag}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    (out / f"{stem}.json").write_text(json.dumps({
        "version": __version__, "commit": git_commit(), "date": datetime.now().isoformat(timespec="seconds"),
        "executors": args.executors, "profiles": args.profiles, "language": args.language, "levels": args.levels,
        "rows": [asdict(r) for r in rows]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {(out / stem).relative_to(ROOT.parent)}.csv (+ .json)")
    from eval.resilience.report import print_tables
    print_tables([asdict(r) for r in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
