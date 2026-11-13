"""
A second annotator for the closed request sets (decided on 13/11/2026, before the final run).

    python -m eval.second_annotator draw                 # the draw: 25% of each closed set, by page
    python -m eval.second_annotator status               # how many drawn tasks are annotated, per set
    python -m eval.second_annotator kappa RESULTS.csv... # after the final run: the two keys' agreement

draw     A seeded draw (seed 20261113) of 25% of the tasks of each closed request set present (the synthetic,
         the synthetic controlled and, once drawn, the human), stratified by page: each page gets its share,
         rounded so the set's total is 25% of it (largest remainder). For the drawn tasks it writes clean
         skeletons in eval/plans/second_annotator/<set>_tasks.json, made the same way as the first
         annotator's (the synthetic: empty; the synthetic controlled and the human: with every page's
         negative checks prefilled, as eval.closed_sets does), with nothing of the first answer key. It never
         overwrites a set already drawn, so it can run again when the human set exists.
status   Counts, per set, the drawn tasks and the annotated ones (with a reference plan, or marked
         impossible). Prints no request.
kappa    Reads the final run's results: every run of a drawn task was judged by both keys (plan_run records
         success_2, see second_key_success there), and Cohen's kappa between the two is computed per set,
         executor and model, and over all.

The second annotator annotates with the first one's method in each set: by hand in the synthetic one; with
the local annotation helper in the synthetic controlled and the human. The second answer key freezes on
01/12/2026, with the first. The drawn files are closed-set files: never print their requests.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLANS = ROOT / "plans"
OUT = PLANS / "second_annotator"
SEED = 20261113
SHARE = 0.25
SETS = {                                       # set -> (its closed file, whether its skeletons get the negatives)
    "synthetic": (PLANS / "holdout_tasks.json", False),
    "synthetic_controlled": (PLANS / "holdout_controlled_tasks.json", True),
    "human": (PLANS / "holdout_human_tasks.json", True),
}
# What a skeleton keeps of a task: who wrote it, where, and the request. Nothing of the answer key.
KEEP = ("id", "split", "origin", "generator", "author", "language", "fixture", "request", "filled")


def allocation(by_page: dict[str, int], share: float = SHARE) -> dict[str, int]:
    """How many tasks each page gets: its share rounded down, then one more for the largest remainders
    (ties by page name), so that the set's total is share x its size, rounded half up (42 tasks: 11)."""
    total = math.floor(share * sum(by_page.values()) + 0.5)
    quota = {p: math.floor(share * n) for p, n in by_page.items()}
    left = total - sum(quota.values())
    order = sorted(by_page, key=lambda p: (-(share * by_page[p] - quota[p]), p))
    for p in order[:max(0, left)]:
        quota[p] += 1
    return quota


def draw_set(name: str, tasks: list[dict]) -> list[dict]:
    """The drawn tasks of one set, as clean skeletons (in the set's order)."""
    pages = defaultdict(list)
    for t in tasks:
        pages[t["fixture"]].append(t["id"])
    quota = allocation({p: len(ids) for p, ids in pages.items()})
    rng = random.Random(f"{SEED}:{name}")
    chosen = set()
    for page in sorted(pages):
        chosen |= set(rng.sample(sorted(pages[page]), quota[page]))
    skeletons = []
    for t in tasks:
        if t["id"] in chosen:
            s = {k: t[k] for k in KEEP if k in t}
            s.update({"checks": [], "allowed": [], "reference": [], "note": "to annotate (second annotator)"})
            skeletons.append(s)
    return skeletons


def path_of(name: str) -> Path:
    return OUT / f"{name}_tasks.json"


def shown(path: Path) -> str:
    """A path as printed: relative to the repository when it is inside it."""
    try:
        return str(path.relative_to(ROOT.parent))
    except ValueError:
        return str(path)


def draw() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (source, negatives) in SETS.items():
        target = path_of(name)
        if target.exists():
            print(f"{name}: already drawn ({shown(target)}), left as it is")
            continue
        if not source.exists():
            print(f"{name}: no closed set yet ({source.name}); draw it again when there is")
            continue
        tasks = json.loads(source.read_text(encoding="utf-8"))["tasks"]
        skeletons = draw_set(name, tasks)
        target.write_text(json.dumps({
            "_readme": f"Second annotator: {len(skeletons)} of the {len(tasks)} tasks of {source.name} ({SHARE:.0%}, "
                       f"by page, seed {SEED}), drawn by python -m eval.second_annotator draw. Clean skeletons: "
                       "nothing of the first answer key. Annotated with the first annotator's method; frozen on "
                       "01/12/2026.",
            "tasks": skeletons}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if negatives:
            from eval.closed_sets import prefill_negatives
            prefill_negatives(target)
        print(f"{name}: {len(skeletons)} of {len(tasks)} tasks drawn, from {len({t['fixture'] for t in skeletons})} "
              f"pages, into {shown(target)}")
    return 0


def annotated(task: dict) -> bool:
    return bool(task.get("reference") or task.get("expected"))


def status() -> int:
    for name in SETS:
        target = path_of(name)
        if not target.exists():
            print(f"{name}: not drawn yet")
            continue
        tasks = json.loads(target.read_text(encoding="utf-8"))["tasks"]
        print(f"{name}: {sum(annotated(t) for t in tasks)} of {len(tasks)} annotated")
    return 0


def second_keys() -> dict[str, dict]:
    """The second answer key of every drawn task already annotated: id -> its key fields."""
    keys = {}
    for name in SETS:
        target = path_of(name)
        if target.exists():
            for t in json.loads(target.read_text(encoding="utf-8"))["tasks"]:
                if annotated(t):
                    keys[t["id"]] = {k: t[k] for k in ("checks", "allowed", "extraction", "expected", "reference") if k in t}
    return keys


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa between two binary judgements of the same runs."""
    n = len(pairs)
    if not n:
        return None
    both = sum(1 for a, b in pairs if a and b)
    neither = sum(1 for a, b in pairs if not a and not b)
    first, second = sum(a for a, _ in pairs), sum(b for _, b in pairs)
    observed = (both + neither) / n
    expected = (first * second + (n - first) * (n - second)) / n ** 2
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def kappa(files: list[Path]) -> int:
    groups = defaultdict(list)
    for path in files:
        for row in csv.DictReader(open(path, encoding="utf-8")):
            if row.get("success_2") not in ("True", "False"):
                continue
            pair = (row["success"] == "True", row["success_2"] == "True")
            groups[(row.get("origin") or "synthetic", row.get("executor") or "anchor", row["profile"])].append(pair)
            groups[("all", "", "")].append(pair)
    if not groups:
        print("no run judged by both keys in these files")
        return 1
    print(f"{'set':22} {'executor':18} {'model':14} {'runs':>5} {'agree':>6} {'kappa':>6}")
    for (s, ex, model), pairs in sorted(groups.items()):
        k = cohen_kappa(pairs)
        agree = sum(a == b for a, b in pairs) / len(pairs)
        print(f"{s:22} {ex:18} {model:14} {len(pairs):5} {agree:6.1%} {'—' if k is None else f'{k:6.3f}'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.second_annotator", description="The second annotator.")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("draw", help="draw 25% of each closed set, by page, into clean skeletons")
    sub.add_parser("status", help="how many drawn tasks are annotated")
    k = sub.add_parser("kappa", help="the agreement of the two keys on the final run's results")
    k.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    if args.command == "draw":
        return draw()
    if args.command == "status":
        return status()
    return kappa(args.files)


if __name__ == "__main__":
    sys.exit(main())
