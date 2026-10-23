"""
The closed sets' sources: reading the generators' sheets and making the tasks file to annotate.

    python -m eval.closed_sets skeleton eval/synthetic_controlled_2026-10-22 synthetic_controlled

writes eval/plans/holdout_controlled_tasks.json with one task per request (split "test"), its origin
and its generator, and empty checks for the person to annotate.

    python -m eval.closed_sets page-items synthetic

prints, per generator, how many requests cite an item of their page's visible text (counts only). Nothing here prints a request: these
are closed sets (eval/README.md), not to be looked at by the system before the final run.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LITERAL_BOM = "\\xef\\xbb\\xbf"          # the package's header had these 12 characters as text

# Results come out with and without these generators too (a sensitivity analysis decided before any
# annotation or run, and recorded in the set's PROCEDENCIA.md).
SENSITIVITY = {"synthetic_controlled": ("chatgpt",)}
# ...and without these tasks (decided on 23/10/2026, before the final run, eval/README.md): in the
# synthetic set, the two requests identical, word for word, to an example of the 08/10 LEIA-ME.
EXCLUDED_TASKS = {"synthetic": ("without the LEIA-ME copies", ("t-ord-a1", "t-ord-c1"))}

STOPWORDS = set("""a o as os um uma uns umas de do da dos das em no na nos nas para por com sem que e ou se ao aos
the an and or of to in on for with by at is are be this that it from as all""".split())


def _words(text: str) -> set:
    import unicodedata
    plain = "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn").lower()
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) >= 3 and w not in STOPWORDS}


def page_items(tasks: list[dict], page_texts: dict[str, str]) -> dict[str, list[int]]:
    """
    Per generator, [requests, requests that cite an item of their page]: a word of the page's visible
    text that is on no other page of the same set (a room, a person, a product, a ticket number...),
    so it shows the generator read that page. Counts only: no request is returned.
    """
    vocab = {f: _words(page_texts[f]) for f in {t["fixture"] for t in tasks}}
    specific = {f: vocab[f] - set().union(*(v for g, v in vocab.items() if g != f)) for f in vocab}
    out: dict[str, list[int]] = {}
    for t in tasks:
        row = out.setdefault(t.get("generator") or "?", [0, 0])
        row[0] += 1
        row[1] += bool(_words(t["request"]) & specific[t["fixture"]])
    return dict(sorted(out.items()))


def read_sheet(path: Path) -> list[dict]:
    """A generator's sheet ("pagina;pedido"), as [{"line": "P01", "page": "reservas.html", "request": ...}]."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    if text.startswith(LITERAL_BOM):
        text = text[len(LITERAL_BOM):]
    first = text.splitlines()[0] if text else ""
    delimiter = ";" if first.count(";") >= first.count(",") else ","
    rows = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delimiter):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k is not None}
        where = row.get("pagina") or row.get("página") or row.get("page") or ""
        request = row.get("pedido") or row.get("request") or ""
        found = re.match(r"\s*(P\d+)\s+(\S+\.html)\s*$", where)
        rows.append({"line": found.group(1) if found else "", "page": found.group(2) if found else where, "request": request})
    return rows


def skeleton(folder: Path, origin: str, fixtures: str = "collection") -> list[dict]:
    """One task per request of every sheet in folder/planilhas, ready to annotate."""
    tasks = []
    for sheet in sorted((Path(folder) / "planilhas").glob("*.csv")):
        generator = sheet.stem
        seen: dict[str, int] = {}
        for row in read_sheet(sheet):
            seen[row["line"]] = seen.get(row["line"], 0) + 1
            tasks.append({
                "id": f"{origin[:2]}-{generator}-{row['line'].lower()}-{seen[row['line']]}",
                "split": "test", "origin": origin, "generator": generator, "language": "pt",
                "fixture": f"{fixtures}/{row['page']}", "request": row["request"],
                "checks": [], "allowed": [], "reference": [], "note": "to annotate",
            })
    return tasks


def page_items_report(origin: str) -> int:
    """Prints, per generator of a closed set, how many requests cite an item of their page (counts only)."""
    from playwright.sync_api import sync_playwright

    from eval.plan_run import FIXTURES, load_tasks
    tasks = [t for t in load_tasks() if t.get("split") == "test" and t.get("origin") == origin]
    texts = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for f in sorted({t["fixture"] for t in tasks}):
            page = browser.new_page()
            page.goto((FIXTURES / f).as_uri())
            texts[f] = page.inner_text("body")
            page.close()
        browser.close()
    for generator, (n, cited) in page_items(tasks, texts).items():
        print(f"{origin} / {generator}: {cited} of {n} requests cite an item of their page ({cited / n:.0%})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "page-items":
        return page_items_report(argv[1])
    if len(argv) != 3 or argv[0] != "skeleton":
        print(__doc__)
        return 2
    folder, origin = Path(argv[1]), argv[2]
    out = ROOT / "plans" / "holdout_controlled_tasks.json"
    if out.exists():
        print(f"{out} already exists: it may already be annotated, so it is not written over.")
        return 1
    tasks = skeleton(folder, origin)
    out.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by = {}
    for t in tasks:
        by[t["generator"]] = by.get(t["generator"], 0) + 1
    print(f"{len(tasks)} tasks written to {out} ({', '.join(f'{g}: {n}' for g, n in sorted(by.items()))}); "
          "annotate each one's checks before the final run.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
