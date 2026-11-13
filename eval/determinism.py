"""
Are two runs of the same evaluation identical? (decided on 13/11/2026, before the final run)

    python -m eval.determinism FIRST.csv SECOND.csv

Compares two result files of the same command (plan_run or resilience.run), run by run: the result, the
false success, the unrequested steps and the steps themselves. The rule registered before the final run: if
each executor's two development runs are identical, the final run makes one run per combination; if not,
three. It prints counts and the ids of the runs that differ (development tasks only: never point it at
closed-set results before the final run).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# what identifies a run, and what must be the same in both files (plan_run's and resilience.run's columns)
KEY = ("executor", "profile", "task", "run", "language")
SAME = ("success", "premature", "false_success", "claimed_success", "unrequested", "attacked", "plan", "steps")


def rows_of(path: Path) -> dict[tuple, dict]:
    rows = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        rows[tuple(row.get(k, "") for k in KEY)] = row
    return rows


def compare(first: dict, second: dict) -> tuple[list, list, list]:
    """(the runs in both files that differ, with the fields that differ), the runs only in the first, only in the second."""
    differ = []
    for key in sorted(set(first) & set(second)):
        fields = [f for f in SAME if f in first[key] and first[key].get(f) != second[key].get(f)]
        if fields:
            differ.append((key, fields))
    return differ, sorted(set(first) - set(second)), sorted(set(second) - set(first))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.determinism", description="Are two runs of the same evaluation identical?")
    ap.add_argument("first", type=Path)
    ap.add_argument("second", type=Path)
    args = ap.parse_args(argv)
    first, second = rows_of(args.first), rows_of(args.second)
    differ, only_first, only_second = compare(first, second)
    both = len(set(first) & set(second))
    print(f"{both} runs in both files; {both - len(differ)} identical, {len(differ)} different; "
          f"{len(only_first)} only in the first, {len(only_second)} only in the second")
    for key, fields in differ:
        print(f"  differs: {key[0]} {key[1] or '-'} {key[2]} run {key[3] or '1'}: {', '.join(fields)}")
    identical = not differ and not only_first and not only_second
    print("IDENTICAL" if identical else "NOT IDENTICAL")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
