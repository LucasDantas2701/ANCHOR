"""
The draw of the human closed set: 60 requests from the collection's Google Forms export.

    python -m eval.human_sample <export.csv>

It must run from this file exactly as committed (it refuses otherwise), so the draw is the one the
commit fixed before anyone read a response. It writes eval/plans/holdout_human_tasks.json (the
tasks to annotate, with empty checks) and eval/plans/holdout_human_sample.json (how the draw went:
the commit, the seed, the input's hash, counts and completions; no request), and prints only counts.

The rules, fixed here before the responses were read (this version, revised on 23/10/2026 before any
response was read: the pilot's response excluded, and the two request fields of five pages read):
- discarded: the pilot (the form's test before it went out, sent at 22/10/2026 13:18:01, if it is
  still in the export); whoever answered "Não concordo" to the consent; whoever did not say if they
  work in IT;
- a request is one non-empty answer to a page's request field ("Pxx · Pedido", or "Pxx · Pedido 1"
  and "Pxx · Pedido 2"; the page is the code P01–P09); "Pxx · Você abriu o link desta página?" is
  kept with it;
- 30 requests from people who work in IT and 30 from people who do not, each profile spread over
  the 9 pages: 3 per page, and the 3 left go to pages drawn with the seed;
- within a stratum (profile and page), the requests are drawn with the seed, from the responses in
  the order of the sheet's rows, one per person first: a person's second request on that page is
  taken only when there are not enough different people;
- when a stratum has too few: first the other profile on the same page, then the same profile on
  another page (the one with most requests left), then the other profile on another page; every
  completion is recorded.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = 20261022
PER_PROFILE = 30
PROFILES = ("it", "non_it")
# The collection's page codes, as in its instructions and in eval/fixtures/collection/.
PAGES = {"P01": "reservas.html", "P02": "suporte.html", "P03": "blog.html", "P04": "rh.html", "P05": "cadastro.html",
         "P06": "usuarios.html", "P07": "pedidos.html", "P08": "vagas.html", "P09": "loja.html"}
TASKS_OUT = ROOT / "plans" / "holdout_human_tasks.json"
REPORT_OUT = ROOT / "plans" / "holdout_human_sample.json"
LITERAL_BOM = "\\xef\\xbb\\xbf"
# The form's test response, sent before the form went out (local time of the form, Manaus).
PILOT_AT = ("2026-10-22 13:18:01",)


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn").lower().strip()


def _yes(value: str):
    v = _plain(value)
    if v.startswith(("sim", "yes")):
        return True
    if v.startswith(("nao", "no")):
        return False
    return None


def read_export(path: Path) -> list[dict]:
    """The export's rows, as dicts of the original headers (a BOM, real or as text, is left out)."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    if text.startswith(LITERAL_BOM):
        text = text[len(LITERAL_BOM):]
    first = text.splitlines()[0] if text else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def when(value: str) -> str:
    """A response's time as "YYYY-MM-DD HH:MM:SS", from the Sheets ("22/10/2026 13:18:01") or the
    Forms download ("2026/10/22 1:18:01 PM GMT-4") format; "" when it is neither."""
    v = (value or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})", v)
    if m:
        d, mo, y, h, mi, s = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})[ T](\d{1,2}):(\d{2}):(\d{2})\s*([AaPp][Mm])?", v)
    if m:
        y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
        ampm = (m.group(7) or "").lower()
        if ampm == "pm" and h < 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
    return ""


def columns(header: list[str]) -> dict:
    """Which column is the time, the consent, the profile, each page's request fields and each
    page's "abriu o link" (the titles of criar_formulario.gs, in eval/fixtures/collection/)."""
    found = {"time": None, "consent": None, "profile": None, "requests": {}, "opened": {}, "opened_any": None}
    for name in header:
        plain = _plain(name)
        code = re.search(r"\bp0?([1-9])\b", plain)
        opened = "abriu" in plain or "link" in plain
        if code:
            key = f"P0{code.group(1)}"
            if opened:
                found["opened"][key] = name
            else:
                found["requests"].setdefault(key, []).append(name)
        elif opened:
            found["opened_any"] = name
        elif "carimbo" in plain or "timestamp" in plain or "data/hora" in plain:
            found["time"] = name
        elif "concord" in plain or "consent" in plain:
            found["consent"] = name
        elif re.search(r"\bti\b|tecnologia da informacao", plain):
            found["profile"] = name
    return found


def candidates(rows: list[dict], cols: dict) -> tuple[list[dict], dict]:
    """Every request that can be drawn, and how many rows were left out and why."""
    out, left_out = [], {"pilot": 0, "did_not_agree": 0, "no_profile": 0}
    for number, row in enumerate(rows, start=2):                # row 1 is the header
        if cols["time"] and when(row.get(cols["time"], "")) in PILOT_AT:
            left_out["pilot"] += 1
            continue
        if cols["consent"] and "nao concordo" in _plain(row.get(cols["consent"], "")):
            left_out["did_not_agree"] += 1
            continue
        works_in_it = _yes(row.get(cols["profile"], "")) if cols["profile"] else None
        if works_in_it is None:
            left_out["no_profile"] += 1
            continue
        for code in sorted(cols["requests"]):
            opened_col = cols["opened"].get(code) or cols["opened_any"]
            for field in cols["requests"][code]:
                request = (row.get(field) or "").strip()
                if not request:
                    continue
                position = re.search(r"pedido\s*(\d)", _plain(field))
                out.append({"row": number, "code": code, "profile": "it" if works_in_it else "non_it",
                            "position": int(position.group(1)) if position else 1, "request": request,
                            "opened_link": _yes(row.get(opened_col, "")) if opened_col else None})
    return out, left_out


def draw(pool: list[dict], seed: int = SEED) -> tuple[list[dict], dict]:
    """The stratified draw (the module's docstring has the rules): the chosen requests and the record."""
    rng = random.Random(seed)
    codes = sorted(PAGES)
    quota = {}
    for profile in PROFILES:
        extra = set(rng.sample(codes, PER_PROFILE - 3 * len(codes)))
        for code in codes:
            quota[(profile, code)] = 3 + (code in extra)
    left = {}
    for profile in PROFILES:
        for code in codes:
            mine = sorted((c for c in pool if c["profile"] == profile and c["code"] == code),
                          key=lambda c: (c["row"], c.get("position", 1)))
            rng.shuffle(mine)
            # One request per person first; a person's other request on the page only afterwards.
            seen, first, second = set(), [], []
            for c in mine:
                (second if c["row"] in seen else first).append(c)
                seen.add(c["row"])
            left[(profile, code)] = first + second
    chosen, completions = [], []

    def take(key, n, stratum, how):
        got = left[key][:n]
        left[key] = left[key][n:]
        for c in got:
            chosen.append({**c, "stratum": f"{stratum[0]}/{stratum[1]}", "filled": how})
        if got and how:
            completions.append({"stratum": f"{stratum[0]}/{stratum[1]}", "from": f"{key[0]}/{key[1]}", "how": how, "count": len(got)})
        return len(got)

    for profile in PROFILES:
        other = PROFILES[1 - PROFILES.index(profile)]
        for code in codes:
            need = quota[(profile, code)] - take((profile, code), quota[(profile, code)], (profile, code), "")
            if need:
                need -= take((other, code), need, (profile, code), "other_profile_same_page")
            while need:
                same = max(((profile, c) for c in codes if left[(profile, c)]), key=lambda k: (len(left[k]), k[1]), default=None)
                any_ = max(((other, c) for c in codes if left[(other, c)]), key=lambda k: (len(left[k]), k[1]), default=None)
                source = same or any_
                if source is None:
                    completions.append({"stratum": f"{profile}/{code}", "from": None, "how": "not_enough_requests", "count": need})
                    break
                need -= take(source, 1, (profile, code), "same_profile_other_page" if source == same else "other_profile_other_page")
    available = {f"{p}/{c}": sum(1 for x in pool if x["profile"] == p and x["code"] == c) for p in PROFILES for c in codes}
    record = {"seed": seed, "quota": {f"{p}/{c}": quota[(p, c)] for p in PROFILES for c in codes},
              "available": available, "completions": completions, "drawn": len(chosen)}
    return chosen, record


def tasks_of(chosen: list[dict]) -> list[dict]:
    tasks, seen = [], {}
    for c in chosen:
        base = f"hu-{c['code'].lower()}-{c['profile']}"
        seen[base] = seen.get(base, 0) + 1
        tasks.append({"id": f"{base}-{seen[base]}", "split": "test", "origin": "human", "generator": c["profile"],
                      "language": "pt", "fixture": f"collection/{PAGES[c['code']]}", "request": c["request"],
                      "field": c.get("position", 1),
                      "opened_link": c["opened_link"], "response_row": c["row"], "stratum": c["stratum"],
                      "filled": c["filled"] or None, "checks": [], "allowed": [], "reference": [], "note": "to annotate"})
    return tasks


def _committed() -> str:
    """The commit this file comes from, or "" when the file differs from it (or is not committed)."""
    try:
        here = Path(__file__).resolve()
        top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=here.parent, text=True).strip())
        rel = here.relative_to(top).as_posix()
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=top).returncode != 0:
            return ""
        if subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=top, capture_output=True).returncode != 0:
            return ""
        return subprocess.check_output(["git", "log", "-1", "--format=%H", "--", rel], cwd=top, text=True).strip()
    except Exception:
        return ""


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    commit = _committed()
    if not commit:
        print("This script must run exactly as committed (commit it, with no change, before the draw).")
        return 1
    if TASKS_OUT.exists() or REPORT_OUT.exists():
        print("The draw was already made (its files exist): it is made once, and not written over.")
        return 1
    path = Path(argv[0])
    rows = read_export(path)
    cols = columns(list(rows[0].keys()) if rows else [])
    missing = sorted(set(PAGES) - set(cols["requests"]))
    if missing or not cols["profile"]:
        print(f"The export's questions were not recognised (pages without a column: {missing}; profile: {bool(cols['profile'])}).")
        return 1
    pool, left_out = candidates(rows, cols)
    chosen, record = draw(pool)
    TASKS_OUT.write_text(json.dumps({"tasks": tasks_of(chosen)}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    REPORT_OUT.write_text(json.dumps({
        "script_commit": commit, "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows), "left_out": left_out, "requests_available": len(pool), **record,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by = {p: sum(1 for c in chosen if c["profile"] == p) for p in PROFILES}
    print(f"{len(rows)} responses; left out: {left_out}; {len(pool)} requests available; "
          f"drawn {len(chosen)} ({by['it']} IT, {by['non_it']} not IT); completions: {len(record['completions'])}.")
    print(f"Written: {TASKS_OUT.name} (to annotate) and {REPORT_OUT.name} (how the draw went).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
