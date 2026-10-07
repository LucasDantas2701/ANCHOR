"""
The resilience benchmark's tables, put together from the parts' results.

    python -m eval.resilience.report eval/results/resilience_*.json

Rows are grouped by executor (and model): the traditional script; the LLM in control; ANCHOR's
recovery (1st run on the altered page) and reuse (2nd run, counted only if it needed no model).
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from statistics import mean


def label(row: dict) -> str | None:
    if row["executor"] == "script":
        return "script"
    if row["executor"] == "llm":
        return f"llm ({row['profile']})"
    return f"anchor {'recovery' if row['run'] == 1 else 'reuse'} ({row['profile']})"


def _ok(row: dict) -> bool:
    # Reuse counts only when the corrected plan worked again without the model.
    if row["executor"] == "anchor" and row["run"] == 2:
        return row["success"] and row["llm_calls"] == 0
    return row["success"]


def print_tables(rows: list[dict]) -> dict:
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(label(r), r["language"])].append(r)
    levels = sorted({r["level"] for r in rows})
    summary = {}
    print("\nSUCCESS PER LEVEL" + "  (anchor reuse: done again with no model call)")
    print(f"{'executor':34} {'lang':>4} " + " ".join(f"{'L' + str(lv):>6}" for lv in levels) + f" {'all':>6}")
    for (name, lang), part in sorted(groups.items()):
        per = {lv: [r for r in part if r["level"] == lv] for lv in levels}
        cells = [f"{sum(_ok(r) for r in per[lv]) / len(per[lv]):6.0%}" if per[lv] else f"{'—':>6}" for lv in levels]
        total = sum(_ok(r) for r in part) / len(part)
        print(f"{name:34} {lang:>4} " + " ".join(cells) + f" {total:6.0%}")
        summary[f"{name} [{lang}]"] = {
            "success": total, "per_level": {lv: (sum(_ok(r) for r in per[lv]) / len(per[lv]) if per[lv] else None)
                                            for lv in levels},
            "false_success": sum(r["false_success"] for r in part), "unrequested": sum(r["unrequested"] for r in part),
            "attacked": sum(r["attacked"] for r in part), "attack_attempts": sum(r["attack_attempts"] for r in part),
            "llm_calls": mean(r["llm_calls"] for r in part), "seconds": mean(r["seconds"] for r in part),
            "healed": sum(r.get("healed", False) for r in part), "runs": len(part)}
    print("\nSAFETY AND COST")
    print(f"{'executor':34} {'lang':>4} {'false ok':>9} {'unreq.':>7} {'attacked':>9} {'attempts':>9} "
          f"{'LLM/run':>8} {'s/run':>7} {'healed':>7}")
    for key, s in summary.items():
        name, lang = key.rsplit(" [", 1)
        print(f"{name:34} {lang[:-1]:>4} {s['false_success']:9} {s['unrequested']:7} {s['attacked']:9} "
              f"{s['attack_attempts']:9} {s['llm_calls']:8.1f} {s['seconds']:7.1f} {s['healed']:7}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.resilience.report")
    ap.add_argument("files", nargs="+", help="result files of eval.resilience.run (.json); patterns are expanded")
    args = ap.parse_args()
    rows = []
    for pattern in args.files:
        for path in sorted(glob.glob(pattern)) or [pattern]:
            rows += json.loads(open(path, encoding="utf-8").read())["rows"]
    if not rows:
        print("No rows.")
        return 1
    print_tables(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
