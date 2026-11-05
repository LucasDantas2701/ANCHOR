"""
The human collection's publication: the whole export, as the form's consent allows, after the draw.

    python -m eval.human_publish <export.csv> [--removals <removals.csv>]

It writes eval/human_collection/responses.csv: one row per response, numbered by its place in the
export BEFORE anything is left out (the numbers of whoever answered "Não concordo", and of the pilot,
are simply missing), without the time it was sent, with the profile, every "abriu o link" and every
request, and, in "drawn", the tasks of the human closed set drawn from it. It runs after the draw
(eval/human_sample.py, which it reads) and prints only counts, never a request.

Accidental personal data is removed by the person who checks the responses, after the draw and
before the annotation: removals.csv, kept OUTSIDE the repository because it holds the data itself,
has one line per removal (response;field;text;type, the field as the question's title, like
"P03 · Pedido 2"). Each text is replaced by "[removido: type]" in the publication and, when the
request was drawn, in its task; eval/human_collection/removals.csv records the response, the field,
the type and the task affected, never the text. Nothing is rewritten with an invented value.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from pathlib import Path

from eval.human_sample import PAGES, PILOT_AT, TASKS_OUT, _plain, columns, read_export, when

OUT = Path(__file__).resolve().parent / "human_collection"


def number(rows: list[dict], cols: dict) -> list[tuple[int, dict]]:
    """(the response's number, its row) for every response that may be published, in export order."""
    kept = []
    for n, row in enumerate(rows, start=1):
        if cols["time"] and when(row.get(cols["time"], "")) in PILOT_AT:
            continue
        if cols["consent"] and "nao concordo" in _plain(row.get(cols["consent"], "")):
            continue
        kept.append((n, row))
    return kept


def field_of(title: str) -> tuple[str, int]:
    """("P03", 2) for "P03 · Pedido 2"; ("P05", 1) for "P05 · Pedido"."""
    plain = _plain(title)
    code = re.search(r"\bp0?([1-9])\b", plain)
    pos = re.search(r"pedido\s*(\d)", plain)
    return (f"P0{code.group(1)}" if code else "", int(pos.group(1)) if pos else 1)


def publish(export: Path, removals: Path | None = None, tasks_path: Path = TASKS_OUT, out: Path = OUT) -> dict:
    rows = read_export(export)
    cols = columns(list(rows[0].keys()) if rows else [])
    tasks = json.loads(Path(tasks_path).read_text(encoding="utf-8"))["tasks"]
    drawn: dict[int, list[str]] = {}
    for t in tasks:
        drawn.setdefault(t["response_row"] - 1, []).append(t["id"])     # the sheet's row 1 is its header
    kept = number(rows, cols)
    header = ["response", cols["profile"]] + [c for code in sorted(PAGES) for c in
                                              ([cols["opened"].get(code)] if cols["opened"].get(code) else [])
                                              + cols["requests"].get(code, [])] + ["drawn"]
    table = {n: {**{c: (row.get(c) or "") for c in header if c not in ("response", "drawn")}, "response": n,
                 "drawn": " ".join(sorted(drawn.get(n, [])))} for n, row in kept}
    log = []
    if removals:
        text = Path(removals).read_bytes().decode("utf-8-sig")
        for line in csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") >= text.count(",") else ","):
            n, field, what, kind = int(line["response"]), line["field"].strip(), line["text"], line["type"].strip()
            if n not in table or field not in table[n] or what not in table[n][field]:
                raise SystemExit(f"Removal not applied: response {n}, field {field!r} (the text is not there).")
            mark = f"[removido: {kind}]"
            table[n][field] = table[n][field].replace(what, mark)
            code, pos = field_of(field)
            affected = [t for t in tasks if t["response_row"] - 1 == n and code and t["fixture"] == f"collection/{PAGES[code]}"
                        and t.get("field", 1) == pos]
            for t in affected:
                t["request"] = t["request"].replace(what, mark)
                t.setdefault("removals", []).append(kind)
            log.append({"response": n, "field": field, "type": kind, "task": " ".join(t["id"] for t in affected)})
        if any(entry["task"] for entry in log):
            Path(tasks_path).write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "responses.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter=";")
        w.writeheader()
        for n in sorted(table):
            w.writerow(table[n])
    with open(out / "removals.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["response", "field", "type", "task"], delimiter=";")
        w.writeheader()
        w.writerows(log)
    return {"responses": len(rows), "published": len(kept), "left_out": len(rows) - len(kept),
            "with_drawn": sum(1 for n in table if table[n]["drawn"]), "removals": len(log),
            "tasks_affected": sum(1 for entry in log if entry["task"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publishes the human collection (after the draw).")
    ap.add_argument("export")
    ap.add_argument("--removals", help="the removals, kept outside the repository (response;field;text;type)")
    args = ap.parse_args(argv)
    if not TASKS_OUT.exists():
        print("The draw has not run yet (eval/plans/holdout_human_tasks.json): publish after it.")
        return 1
    done = publish(Path(args.export), Path(args.removals) if args.removals else None)
    print(f"{done['responses']} responses; {done['published']} published, {done['left_out']} left out; "
          f"{done['with_drawn']} with drawn requests; {done['removals']} removals, {done['tasks_affected']} in drawn tasks.")
    print(f"Written: {OUT.relative_to(OUT.parent.parent)}/responses.csv and removals.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
