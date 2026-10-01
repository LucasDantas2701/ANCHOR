"""
Evaluation of the ElementResolver + the Executor's validation.

For each case (page + query + expected element), it measures:

    - the position of the right element in the ranking;
    - what the Executor would decide (success / ambiguous / not_found);
    - whether a failure came from perception (target not even indexed) or ranking.

Usage (from the project root):

    python -m eval.run                   # all cases
    python -m eval.run --split dev       # only the development cases
    python -m eval.run --offline         # skips real sites
    python -m eval.run --site store -v   # one site, showing each case
    python -m eval.run --sweep           # sweeps minimum score × gap
    python -m eval.run --check           # only checks the expected selectors (holdout included)
    python -m eval.run --final           # runs the HOLDOUT (split "test"). Once, at the end.

The "test" split is the closed set (holdout): it is left out of every run
unless --final is used. Do not look at these results during development.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from anchor import __version__
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.action_executor.constants import (
    DEFAULT_AMBIGUITY_GAP,
    DEFAULT_MIN_SCORE,
    RESOLVER_ACTION_MAP,
)
from anchor.engine.element_resolver import ElementResolver
from eval.setups import SETUPS

ROOT = Path(__file__).resolve().parent
KS = (1, 3, 5, 10)
MAX_K = max(KS)


@dataclass
class CaseResult:
    suite: str
    case_id: str
    split: str
    action: str
    query: str
    status: str               # the Executor's decision
    rank: int | None          # target position (1 = first); None = outside the top 10
    target_indexed: bool      # was the target among the indexed elements?
    outcome: str              # see classify()
    top1_score: float
    runner_up_score: float
    target_score: float | None
    top1_is_target: bool
    top1_desc: str
    n_indexed: int
    ms: float


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------

def check_selectors(suites: list[dict]) -> None:
    """Checks that each expected selector finds element(s). Does not compute scores."""
    problems = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for suite in suites:
            page = browser.new_page()
            open_suite(page, suite)
            for case in suite["cases"]:
                n = page.locator(case["expected"]).count()
                if n == 0:
                    problems += 1
                    print(f"  [NO TARGET] {case['id']}: {case['expected']}")
                elif n > 1:
                    print(f"  [warning] {case['id']}: the selector matches {n} elements (all accepted)")
            page.close()
        browser.close()
    total = sum(len(s["cases"]) for s in suites)
    print(f"{total} cases checked, {problems} with a broken selector.")


def load_suites(site: str | None, offline: bool) -> list[dict]:
    suites = []
    for path in sorted((ROOT / "cases").glob("*.json")):
        suite = json.loads(path.read_text(encoding="utf-8"))
        if site and suite["site"] != site:
            continue
        if offline and suite.get("requires_network"):
            continue
        suites.append(suite)
    return suites


def open_suite(page: Page, suite: dict) -> None:
    if "fixture" in suite:
        page.goto((ROOT / "fixtures" / suite["fixture"]).as_uri())
    else:
        page.goto(suite["url"])
    if suite.get("setup"):
        SETUPS[suite["setup"]](page)


def target_ids(page: Page, selector: str) -> tuple[int, set[str]]:
    """How many elements the expected selector finds, and which of them were indexed."""
    ids = page.locator(selector).evaluate_all(
        "els => els.map(e => e.getAttribute('data-er-id'))"
    )
    return len(ids), {i for i in ids if i}


# ----------------------------------------------------------------------
# Evaluating one case
# ----------------------------------------------------------------------

def classify(status: str, rank: int | None, indexed: bool) -> str:
    """
    correct              The Executor decided and chose the target.
    silent_error         The Executor decided, but chose the WRONG element (the worst case).
    avoidable_refusal    The target was 1st, but the Executor refused (threshold too conservative).
    correct_refusal      The Executor refused and the 1st was not the target (it avoided an error).
    perception_failure   The target was not even indexed by the script.
    """
    if not indexed:
        return "perception_failure"
    if status == "success":
        return "correct" if rank == 1 else "silent_error"
    return "avoidable_refusal" if rank == 1 else "correct_refusal"


def run_case(page: Page, suite: dict, case: dict) -> CaseResult:
    resolver = ElementResolver(page, synonyms=suite.get("synonyms"))
    executor = ActionExecutor(page, resolver=resolver, k=MAX_K)
    resolver_action = RESOLVER_ACTION_MAP.get(case["action"], case["action"])

    t0 = time.perf_counter()
    status, _, matches = executor._resolve(case["query"], resolver_action)
    ms = (time.perf_counter() - t0) * 1000
    matches = matches or []

    n_expected, expected = target_ids(page, case["expected"])
    if n_expected == 0:
        raise ValueError(f"{case['id']}: the expected selector finds nothing: {case['expected']}")

    rank = next((i for i, m in enumerate(matches, 1) if m.id in expected), None)
    target = matches[rank - 1] if rank else None
    top1 = matches[0] if matches else None

    return CaseResult(
        suite=suite["site"],
        case_id=case["id"],
        split=case.get("split", "dev"),
        action=case["action"],
        query=case["query"],
        status=status,
        rank=rank,
        target_indexed=bool(expected),
        outcome=classify(status, rank, bool(expected)),
        top1_score=round(top1.score, 4) if top1 else 0.0,
        runner_up_score=round(matches[1].score, 4) if len(matches) > 1 else 0.0,
        target_score=round(target.score, 4) if target else None,
        top1_is_target=rank == 1,
        top1_desc=(f"{top1.role} '{top1.text or top1.label or top1.hint}'"[:60] if top1 else ""),
        n_indexed=len(resolver._records),
        ms=round(ms, 1),
    )


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------

def summarize(results: list[CaseResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    s = {"n": n}
    for k in KS:
        s[f"recall@{k}"] = sum(r.rank is not None and r.rank <= k for r in results) / n
    s["mrr"] = sum(1 / r.rank for r in results if r.rank) / n
    for outcome in ("correct", "silent_error", "avoidable_refusal", "correct_refusal", "perception_failure"):
        s[outcome] = sum(r.outcome == outcome for r in results) / n
    s["mean_ms"] = sum(r.ms for r in results) / n
    return s


def sweep(results: list[CaseResult]) -> list[dict]:
    """Simulates the Executor with other thresholds, using the scores already computed."""
    rows = []
    for min_score in (0.15, 0.20, 0.30, 0.40, 0.50, 0.60):
        for gap in (0.02, 0.04, 0.06, 0.08, 0.12, 0.16, 0.20, 0.30):
            ok = err = refused = 0
            for r in results:
                # Same rule as the Executor: gap relative to the 1st score.
                margin = (r.top1_score - r.runner_up_score) / r.top1_score if r.top1_score else 0.0
                decided = r.top1_score >= min_score and margin >= gap
                if not decided:
                    refused += 1
                elif r.top1_is_target:
                    ok += 1
                else:
                    err += 1
            n = len(results)
            rows.append({"min_score": min_score, "gap": gap,
                         "correct": ok / n, "silent_error": err / n, "refused": refused / n})
    return rows


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------

def pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def print_summary(title: str, s: dict) -> None:
    if not s["n"]:
        return
    print(f"\n{title}  (n={s['n']})")
    print(f"  recall@1 {pct(s['recall@1'])}   @3 {pct(s['recall@3'])}   "
          f"@5 {pct(s['recall@5'])}   @10 {pct(s['recall@10'])}   MRR {s['mrr']:.3f}")
    print(f"  Executor: correct {pct(s['correct'])} | silent error {pct(s['silent_error'])} | "
          f"avoidable refusal {pct(s['avoidable_refusal'])} | correct refusal {pct(s['correct_refusal'])} | "
          f"perception failure {pct(s['perception_failure'])}")
    print(f"  mean time per query: {s['mean_ms']:.0f} ms")


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "no-git"


def save(results: list[CaseResult], summary: dict, args) -> Path:
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    tag = "_FINAL" if args.final else ""
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{git_commit()}{tag}"
    with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(results[0])))
        w.writeheader()
        w.writerows(asdict(r) for r in results)
    meta = {
        "version": __version__,
        "commit": git_commit(),
        "date": datetime.now().isoformat(timespec="seconds"),
        "filters": {"split": args.split, "site": args.site, "offline": args.offline},
        "thresholds": {"min_score": DEFAULT_MIN_SCORE, "gap": DEFAULT_AMBIGUITY_GAP},
        "overall": summary,
    }
    (out / f"{stem}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return out / f"{stem}.csv"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Resolver evaluation")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--site")
    ap.add_argument("--offline", action="store_true", help="skips cases that need the internet")
    ap.add_argument("--sweep", action="store_true", help="sweeps minimum score × gap")
    ap.add_argument("-v", "--verbose", action="store_true", help="shows each case")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--check", action="store_true", help="only checks the expected selectors")
    ap.add_argument("--final", action="store_true", help="runs the holdout (split test)")
    args = ap.parse_args()

    if args.check:
        check_selectors(load_suites(args.site, args.offline))
        return

    if args.split == "test" and not args.final:
        ap.error('the "test" split is the holdout; use --final (once, at the end of development)')
    if args.final:
        args.split = "test"
        print("*** HOLDOUT: final run. Record the date and the commit of this run. ***")

    results: list[CaseResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        for suite in load_suites(args.site, args.offline):
            page = browser.new_page()
            open_suite(page, suite)
            for case in suite["cases"]:
                split = case.get("split", "dev")
                if args.split and split != args.split:
                    continue
                if not args.split and split == "test":
                    continue  # the holdout is left out by default
                r = run_case(page, suite, case)
                results.append(r)
                if args.verbose:
                    mark = {"correct": "OK ", "silent_error": "ERR", "perception_failure": "PER"}.get(r.outcome, "REC")
                    print(f"[{mark}] {r.case_id:9} rank={str(r.rank):4} {r.status:9} "
                          f"top1={r.top1_score:.2f} 2nd={r.runner_up_score:.2f}  "
                          f"{r.query!r} → {r.top1_desc}")
            page.close()
        browser.close()

    if not results:
        print("No cases selected.")
        return

    summary = summarize(results)
    print_summary("OVERALL", summary)

    by = defaultdict(list)
    for r in results:
        by[f"site: {r.suite}"].append(r)
        by[f"action: {r.action}"].append(r)
    for key in sorted(by):
        print_summary(key, summarize(by[key]))

    if args.sweep:
        print("\nTHRESHOLD SWEEP (lowest silent error first, then highest correct)")
        print("  min_score   gap (relative)   correct   silent error   refused")
        rows = sorted(sweep(results), key=lambda x: (x["silent_error"], -x["correct"]))
        for row in rows[:12]:
            print(f"    {row['min_score']:.2f}     {row['gap']:.2f}   {pct(row['correct'])}      "
                  f"{pct(row['silent_error'])}       {pct(row['refused'])}")

    path = save(results, summary, args)
    print(f"\nResults saved to {path.relative_to(ROOT.parent)} (+ .json with the summary)")


if __name__ == "__main__":
    main()
