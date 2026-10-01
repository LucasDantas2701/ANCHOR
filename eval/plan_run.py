"""
Evaluation of complete tasks: request → plan (LLM) → execution → final state.

Usage (from the project root):

    python -m eval.plan_run --reference                       # hand-written plans (ceiling, no LLM)
    python -m eval.plan_run --profiles ollama-small           # one model
    python -m eval.plan_run --profiles ollama-small ollama-medium -v
    python -m eval.plan_run --agent --profiles ollama-small   # tasks through the full agent loop
    python -m eval.plan_run --check                           # checks the tasks, without calling models
    python -m eval.plan_run --final --profiles ...            # the CLOSED set (once, at the end)

The tasks in eval/plans/holdout_tasks.json (split "test") form the closed set:
they are left out of every run unless --final is used.

Each task runs on a fresh page. There is no disambiguation: when the heuristic
refuses a step, the task stops there (this measures the system without human
help). The old Portuguese options (--perfis, --referencia, --agente, --tarefa,
--sem-pagina) still work.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from anchor import __version__
from anchor.cli import option
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver
from anchor.planner import ConfigError, Plan, Step, get_profile, page_elements, run_plan
from anchor.planner.progress import Progress

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
TASKS = ROOT / "plans" / "tasks.json"
HOLDOUT_TASKS = ROOT / "plans" / "holdout_tasks.json"

# Records clicks and Enter, and prevents navigation (links and form submissions),
# so the page stays open until the checks.
INSTRUMENT = """
window.__er_log = [];
document.addEventListener("click", (e) => {
    window.__er_log.push({ type: "click", el: e.target });
    if (e.target.closest && e.target.closest("a[href]")) e.preventDefault();
}, true);
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter") window.__er_log.push({ type: "enter", el: e.target });
}, true);
document.addEventListener("submit", (e) => e.preventDefault(), true);
for (const type of ["input", "change"]) {
    document.addEventListener(type, (e) => window.__er_log.push({ type, el: e.target }), true);
}
window.__clicked = (sel) => window.__er_log.some((x) => x.type === "click" && x.el.closest && x.el.closest(sel));
// Elements the plan interacted with (click, typing, choice) outside the allowed ones.
window.__unrequested = (allowed) => {
    const seen = new Set(), out = [];
    for (const { type, el } of window.__er_log) {
        if (type === "enter" || !el || !el.closest) continue;
        if (allowed.some((sel) => el.closest(sel))) continue;
        const target = el.closest("a, button, input, select, textarea, [role], [onclick]") || el;
        if (seen.has(target)) continue;
        seen.add(target);
        const name = (target.getAttribute("aria-label") || target.getAttribute("title")
            || target.innerText || target.value || target.id || target.tagName).trim().replace(/\\s+/g, " ");
        out.push(target.tagName.toLowerCase() + ' "' + name.slice(0, 40) + '"');
    }
    return out;
};
window.__entered = (sel) => window.__er_log.some((x) => x.type === "enter" && x.el.closest && x.el.closest(sel));
"""


class ReferencePlanner:
    """Returns the task's reference plan (no LLM)."""

    model = "reference"

    def __init__(self):
        self.current: list = []

    def plan(self, request, url, page_elements=None, history=None, **_) -> Plan:
        # In --agent mode, a replan returns the reference steps still missing
        # ("feito:" or "done:", depending on the planner prompt's language).
        done = sum(1 for h in (history or []) if h.startswith(("feito:", "done:")))
        return Plan(steps=[Step(a, d, v) for a, d, v in self.current[done:]], model=self.model)


@dataclass
class TaskResult:
    profile: str
    model: str
    task: str
    split: str
    plan_valid: bool
    plan_steps: int
    steps_ok: int
    stopped_at: str           # status of the step that failed ("" if all passed)
    checks_ok: int
    checks: int
    success: bool
    unrequested: int          # elements acted on that the task did not ask for
    unrequested_list: str
    clean: bool               # success AND no unrequested step
    seconds: float
    tokens_in: int
    tokens_out: int
    attempts: int
    error: str
    plan: str
    llm_calls: int = 0        # --agent mode only (1 in plan mode)
    replans: int = 0
    no_effect: int = 0        # --agent mode: actions with no effect on the page
    premature: bool = False   # --agent mode: declared success, but the checks failed
    goals: int = 0            # --agent mode: goals defined by the planner
    goals_done: int = 0
    suspicions: int = 0       # --agent mode: expected texts that did not appear


def run_task_agent(page: Page, planner, profile_name: str, task: dict) -> TaskResult:
    """The task run through the agent loop (no human disambiguation)."""
    from anchor.agent import Agent

    page.goto((FIXTURES / task["fixture"]).as_uri())
    if isinstance(planner, ReferencePlanner):
        planner.current = task["reference"]
    result = Agent(page, planner, ActionExecutor(page, resolver=ElementResolver(page)), report=None).run(task["request"])

    checks = [bool(page.evaluate(f"() => Boolean({c})")) for c in task["checks"]]
    unrequested = page.evaluate("(allowed) => window.__unrequested(allowed)", task["allowed"])
    success = result.ok and all(checks)
    done = [r for r in result.records if r.status == "success"]
    stopped = next((r.status for r in reversed(result.records) if r.status != "success"), "")
    return TaskResult(
        profile=profile_name, model=getattr(planner, "model", ""), task=task["id"],
        split=task.get("split", "dev"),
        plan_valid=not result.plan_failed,
        plan_steps=len(result.records), steps_ok=len(done), stopped_at=stopped,
        checks_ok=sum(checks), checks=len(checks), success=success,
        unrequested=len(unrequested), unrequested_list="; ".join(unrequested),
        clean=success and not unrequested,
        seconds=result.seconds, tokens_in=result.tokens_in, tokens_out=result.tokens_out,
        attempts=result.failures, error="" if result.ok else result.message[:300],
        plan=json.dumps([[r.step.action, r.step.description, r.step.value] for r in result.records],
                        ensure_ascii=False),
        llm_calls=result.llm_calls, replans=result.replans,
        no_effect=result.no_effect, premature=result.ok and not all(checks),
        goals=result.goals_total, goals_done=result.goals_done, suspicions=result.suspicions,
    )


def run_task(page: Page, planner, profile_name: str, task: dict, use_page: bool) -> TaskResult:
    page.goto((FIXTURES / task["fixture"]).as_uri())
    resolver = ElementResolver(page)
    language = getattr(planner, "language", "pt")
    elements = page_elements(resolver, request=task["request"], language=language) if use_page else None

    if isinstance(planner, ReferencePlanner):
        planner.current = task["reference"]

    plan: Optional[Plan] = None
    error = ""
    try:
        plan = planner.plan(task["request"], page.url, elements)
    except Exception as exc:  # invalid plan, connection, missing model...
        error = f"{type(exc).__name__}: {exc}"[:300]

    steps_ok, stopped = 0, ""
    if plan is not None:
        for _, result in run_plan(ActionExecutor(page, resolver=resolver), plan):
            if result.status == "success":
                steps_ok += 1
            else:
                stopped = result.status

    checks = [bool(page.evaluate(f"() => Boolean({c})")) for c in task["checks"]]
    unrequested = page.evaluate("(allowed) => window.__unrequested(allowed)", task["allowed"])
    success = plan is not None and all(checks)
    return TaskResult(
        profile=profile_name,
        model=getattr(planner, "model", ""),
        task=task["id"],
        split=task.get("split", "dev"),
        plan_valid=plan is not None,
        plan_steps=len(plan.steps) if plan else 0,
        steps_ok=steps_ok,
        stopped_at=stopped,
        checks_ok=sum(checks),
        checks=len(checks),
        success=success,
        unrequested=len(unrequested),
        unrequested_list="; ".join(unrequested),
        clean=success and not unrequested,
        seconds=plan.latency_s if plan else 0.0,
        tokens_in=plan.tokens_in if plan else 0,
        tokens_out=plan.tokens_out if plan else 0,
        attempts=plan.attempts if plan else 0,
        llm_calls=1 if plan is not None else 0,
        error=error,
        plan=json.dumps([[s.action, s.description, s.value] for s in plan.steps], ensure_ascii=False)
        if plan else "",
    )


def warm_up(planner) -> float:
    """Loads the model before the tasks, so loading does not count in the plans' time."""
    start = time.perf_counter()
    planner.client.chat.completions.create(
        model=planner.model,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        temperature=0,
    )
    return time.perf_counter() - start


def load_tasks() -> list[dict]:
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    if HOLDOUT_TASKS.exists():
        tasks += json.loads(HOLDOUT_TASKS.read_text(encoding="utf-8"))["tasks"]
    return tasks


REQUIRED = ("id", "fixture", "request", "checks", "allowed", "reference")


def check_tasks(tasks: list[dict], browser=None) -> int:
    """Checks the tasks' structure without calling models or the heuristic."""
    if browser is None:
        with sync_playwright() as p:
            b = p.chromium.launch()
            try:
                return check_tasks(tasks, b)
            finally:
                b.close()

    from anchor.planner import ACTIONS

    problems = []
    ids = [t.get("id") for t in tasks]
    problems += [f"repeated id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for t in tasks:
        tid = t.get("id", "?")
        missing = [k for k in REQUIRED if not t.get(k)]
        if missing:
            problems.append(f"{tid}: missing fields {', '.join(missing)}")
            continue
        if not (FIXTURES / t["fixture"]).exists():
            problems.append(f"{tid}: page {t['fixture']} does not exist in eval/fixtures")
            continue
        for a, d, v in t["reference"]:
            if a not in ACTIONS or (ACTIONS[a] and not v):
                problems.append(f"{tid}: invalid reference step: {a} {d!r} {v!r}")
        page = browser.new_page()
        page.add_init_script(INSTRUMENT)
        page.goto((FIXTURES / t["fixture"]).as_uri())
        for sel in t["allowed"]:
            if page.locator(sel).count() == 0:
                print(f"  [warning] {tid}: {sel} is not on the initial page (it may appear later)")
        for c in t["checks"]:
            try:
                page.evaluate(f"() => Boolean({c})")
            except Exception as exc:
                problems.append(f"{tid}: check with an error: {c} ({str(exc).splitlines()[0][:80]})")
        page.close()
    for msg in problems:
        print(f"  [PROBLEM] {msg}")
    n_test = sum(t.get("split") == "test" for t in tasks)
    print(f"{len(tasks)} tasks checked ({n_test} in the closed set), {len(problems)} problem(s).")
    return 1 if problems else 0


def summarize(rows: list[TaskResult]) -> dict:
    n = len(rows)
    valid = [r for r in rows if r.plan_valid]
    return {
        "tasks": n,
        "success": sum(r.success for r in rows) / n,
        "clean": sum(r.clean for r in rows) / n,
        "unrequested": sum(r.unrequested for r in rows),
        "plan_valid": len(valid) / n,
        "checks": sum(r.checks_ok for r in rows) / max(1, sum(r.checks for r in rows)),
        "heuristic_refusals": sum(r.stopped_at in ("ambiguous", "not_found") for r in rows),
        "mean_seconds": mean(r.seconds for r in valid) if valid else 0.0,
        "mean_tokens": mean(r.tokens_in + r.tokens_out for r in valid) if valid else 0.0,
        "mean_attempts": mean(r.attempts for r in valid) if valid else 0.0,
        "mean_llm_calls": mean(r.llm_calls for r in rows),
        "replans": sum(r.replans for r in rows),
        "no_effect": sum(r.no_effect for r in rows),
        "premature": sum(r.premature for r in rows),
        "goals_done": (sum(r.goals_done for r in rows) / sum(r.goals for r in rows)
                       if sum(r.goals for r in rows) else None),
        "suspicions": sum(r.suspicions for r in rows),
    }


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "no-git"


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.plan_run")
    option(ap, "--profiles", "--perfis", nargs="*", default=[], help="profiles from llm_profiles.json")
    option(ap, "--reference", "--referencia", action="store_true", help="includes the hand-written plans")
    option(ap, "--no-page", "--sem-pagina", action="store_true", help="does not send the list of elements to the model")
    option(ap, "--task", "--tarefa", help="runs only one task (id)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--check", action="store_true", help="checks the tasks, without calling models")
    ap.add_argument("--final", action="store_true", help="runs the CLOSED set (split test)")
    option(ap, "--agent", "--agente", action="store_true",
           help="runs the tasks through the agent loop (replanning and end check)")
    option(ap, "--prompt-language", choices=("pt", "en"), help="planner prompt language (default: the profile's)")
    args = ap.parse_args()

    all_tasks = load_tasks()
    if args.check:
        return check_tasks(all_tasks)

    wanted = "test" if args.final else "dev"
    tasks = [t for t in all_tasks if t.get("split", "dev") == wanted]
    if args.final:
        print("*** CLOSED SET: final run. Record the date and the commit of this run. ***")
        if not tasks:
            print("No tasks in the closed set (eval/plans/holdout_tasks.json).")
            return 1
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]

    planners = []
    progress = Progress()
    if args.reference:
        planners.append(("reference", ReferencePlanner()))
    for name in args.profiles:
        try:
            profile = get_profile(name)
            planners.append((name, profile.planner(on_progress=progress.update, prompt_language=args.prompt_language)))
        except ConfigError as exc:
            print(f"[{name}] {exc}")
            return 1
    if not planners:
        ap.error("give --profiles and/or --reference")

    rows: list[TaskResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        warm = {}
        for name, planner in planners:
            print(f"\n=== {name} ({getattr(planner, 'model', '')})")
            is_llm = not isinstance(planner, ReferencePlanner)
            if is_llm:
                progress.prefix = "  loading the model: "
                try:
                    with progress:
                        warm[name] = round(warm_up(planner), 1)
                except Exception as exc:
                    print(f"  this profile cannot be used: {type(exc).__name__}: {exc}")
                    continue
                print(f"  model ready in {warm[name]} s (not counted in the plans' time)")
            for task in tasks:
                page = browser.new_page()
                page.set_default_timeout(5000)
                page.add_init_script(INSTRUMENT)
                progress.prefix = f"  ...   {task['id']:10} "

                def execute():
                    if args.agent:
                        return run_task_agent(page, planner, name, task)
                    return run_task(page, planner, name, task, use_page=not args.no_page)

                if is_llm:
                    with progress:
                        r = execute()
                else:
                    r = execute()
                page.close()
                rows.append(r)
                mark = ("OK " if r.clean else "OK+") if r.success else ("ERR" if not r.plan_valid else "---")
                print(f"[{mark}] {r.task:10} steps {r.steps_ok}/{r.plan_steps} "
                      f"checks {r.checks_ok}/{r.checks} {r.seconds:5.1f}s"
                      + (f"  stopped: {r.stopped_at}" if r.stopped_at else "")
                      + (f"  error: {r.error[:80]}" if r.error else "")
                      + (f"  unrequested: {r.unrequested_list}" if r.unrequested else "")
                      + ("  PREMATURE END" if r.premature else "")
                      + (f"  goals {r.goals_done}/{r.goals}" if r.goals else "")
                      + (f"  suspicions: {r.suspicions}" if r.suspicions else "")
                      + (f"  no effect: {r.no_effect}" if r.no_effect else ""))
                if args.verbose and r.plan:
                    for a, d, v in json.loads(r.plan):
                        print(f"        {a:12} {d}" + (f' = "{v}"' if v is not None else ""))
        browser.close()

    print("\nCOMPARISON")
    print("(clean = tasks done without any unrequested step; OK+ = done, but with an extra step)")
    time_col = "s/task" if args.agent else "s/plan"
    print(f"{'profile':16} {'success':>8} {'clean':>7} {'unreq.':>7} {'plan ok':>8} {'checks':>7} "
          f"{'refusals':>9} {time_col:>8} {'tokens':>7}"
          + (f" {'LLM/task':>9} {'replans':>8} {'no eff.':>8} {'premature':>10} {'goals':>6} {'suspic.':>8}"
             if args.agent else ""))
    summaries = {}
    for name, _ in planners:
        profile_rows = [r for r in rows if r.profile == name]
        if not profile_rows:
            continue
        s = summarize(profile_rows)
        s["load_s"] = warm.get(name)
        summaries[name] = s
        print(f"{name:16} {s['success']:8.0%} {s['clean']:7.0%} {s['unrequested']:7} {s['plan_valid']:8.0%} "
              f"{s['checks']:7.0%} {s['heuristic_refusals']:9} {s['mean_seconds']:8.1f} {s['mean_tokens']:7.0f}"
              + (f" {s['mean_llm_calls']:9.1f} {s['replans']:8} {s['no_effect']:8} {s['premature']:10}"
                 + (f" {s['goals_done']:6.0%}" if s["goals_done"] is not None else f" {'—':>6}")
                 + f" {s['suspicions']:8}" if args.agent else ""))

    if not rows:
        print("No task was run.")
        return 1

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stem = f"plans_{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}" + ("_FINAL" if args.final else "")
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    (out / f"{stem}.json").write_text(json.dumps({
        "version": __version__, "commit": git_commit(), "date": datetime.now().isoformat(timespec="seconds"),
        "page_context": not args.no_page, "mode": "agent" if args.agent else "plan",
        "prompt_language": args.prompt_language or "profile", "summary": summaries,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {(out / stem).relative_to(ROOT.parent)}.csv (+ .json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
