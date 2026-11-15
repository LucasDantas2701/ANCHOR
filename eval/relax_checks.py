"""
Fixed rules that loosen the checks the annotation recorder writes, where the request allows more than one
right outcome (decided on 14/11/2026, before the final run; the same rules for every annotated closed set).

    python -m eval.relax_checks FILE            # shows which tasks a rule would change (ids and rule names)
    python -m eval.relax_checks FILE --write    # applies them

The recorder writes what the annotator did, exactly: the text typed, the date, the time, the option chosen
(and the synthetic set, annotated by hand, has the same kinds of exact checks, in single quotes). That is
right when the request dictates it, and too strict when it does not. The rules, applied by code to each
check of those forms (a field's value compared with a text, a list's chosen option compared with or
starting with a text; any other check is left as it is):

  dictated   a typed text that appears in the request (a name, an e-mail): still exact, but ignoring
             capitals, accents and the spaces at the ends.
  free_text  a typed text that does not appear in the request (a comment in the annotator's words): the field
             is filled, and it contains the content words that the typed text and the request share.
  date       a date field, when the request has a relative date (today, tomorrow, the day after tomorrow,
             next Monday...): the date is computed on the day of the run.
  period     a time field, when the request names a period of the day (morning 06:00-12:00, afternoon
             12:00-18:00, night 18:00-23:59): the time is within it.
  any_option a list choice whose option the request does not name: any option but the first (the prompt).

The request is read only by this code, to look for those words; nothing of it is printed. Closed-set files:
run it on them only as part of the annotation, and never print a request.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# A JavaScript string literal, in double quotes (the recorder's) or in single quotes (written by hand).
_STR = r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
FILL = re.compile(rf"^document\.querySelector\({_STR}\)\.value === {_STR}$")
SELECT = re.compile(rf"^document\.querySelector\({_STR}\)\.selectedOptions\[0\]\.text(?:\.trim\(\))?"
                    rf"(?: === {_STR}|\.startsWith\({_STR}\))$")


def js_string(literal: str) -> str:
    """A JavaScript string literal's value (double or single quotes)."""
    if literal.startswith('"'):
        return json.loads(literal)
    return re.sub(r"\\(.)", r"\1", literal[1:-1])
STOPWORDS = set("""a o as os um uma uns umas de da do das dos em na no nas nos para por com sem que e ou se
mas como mais muito pra pro esta este isso essa esse aquela aquele foi ser sao tem ter the and for with
from that this have has was are you your please """.split())

DAYS = {"domingo": 0, "segunda": 1, "terca": 2, "quarta": 3, "quinta": 4, "sexta": 5, "sabado": 6,
        "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6}
PERIODS = [(r"\bmanha\b|\bmorning\b", ("06:00", "12:00")), (r"\btarde\b|\bafternoon\b", ("12:00", "18:00")),
           (r"\bnoite\b|\bevening\b|\bnight\b", ("18:00", "23:59"))]
NORMALIZE_JS = ".normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').trim().toLowerCase()"


def plain(text: str) -> str:
    """Without accents, in lower case, single spaces."""
    text = unicodedata.normalize("NFD", text)
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").lower().split())


def relative_day(request: str) -> str | None:
    """A JavaScript expression for the date the request means, computed when the check runs, or None."""
    r = plain(request)
    if re.search(r"\bdepois de amanha\b|\bday after tomorrow\b", r):
        offset = 2
    elif re.search(r"\bamanha\b|\btomorrow\b", r):
        offset = 1
    elif re.search(r"\bhoje\b|\btoday\b", r):
        offset = 0
    else:
        for name, day in DAYS.items():
            if re.search(rf"\b(proxima|proximo|next|na|no|on)\s+{name}", r) or re.search(rf"\b{name}(-feira)? que vem\b", r):
                return (f"(d => (d.setDate(d.getDate() + (({day} - d.getDay() + 7) % 7 || 7)), "
                        f"d.toLocaleDateString('sv')))(new Date())")
        return None
    return f"(d => (d.setDate(d.getDate() + {offset}), d.toLocaleDateString('sv')))(new Date())"


def period(request: str) -> tuple[str, str] | None:
    r = plain(request)
    for pattern, span in PERIODS:
        if re.search(pattern, r):
            return span
    return None


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9@.]+", plain(text)) if len(w) >= 4 and w not in STOPWORDS]


def stem(word: str) -> str:
    return word[:6] if len(word) > 6 else word


def relax_check(check: str, request: str, kinds: dict[str, str]) -> tuple[list[str], str | None]:
    """The check, loosened by one rule: (the new checks, the rule's name), or ([check], None)."""
    m = FILL.match(check)
    if m:
        selector, value = js_string(m.group(1)), js_string(m.group(2))
        q = f"document.querySelector({json.dumps(selector)})"
        kind = kinds.get(selector, "text")
        if kind == "date":
            day = relative_day(request)
            return ([f"{q}.value === {day}"], "date") if day else ([check], None)
        if kind == "time":
            span = period(request)
            if span:
                return [f"{q}.value >= '{span[0]}' && {q}.value <= '{span[1]}'"], "period"
            return [check], None
        if kind in ("number", "range", "color", "file", "hidden", "checkbox", "radio"):
            return [check], None
        if plain(value) and plain(value) in plain(request):
            return [f"{q}.value{NORMALIZE_JS} === {json.dumps(plain(value))}"], "dictated"
        shared, seen = [], set()
        request_stems = {stem(w) for w in content_words(request)}
        for w in content_words(value):
            if stem(w) in request_stems and stem(w) not in seen:
                seen.add(stem(w))
                shared.append(stem(w))
        new = [f"{q}.value.trim().length > 0"]
        new += [f"{q}.value{NORMALIZE_JS}.includes({json.dumps(s)})" for s in shared]
        return new, "free_text"
    m = SELECT.match(check)
    if m:
        selector, option = js_string(m.group(1)), js_string(m.group(2) or m.group(3))
        if plain(option) and plain(option) not in plain(request) and plain(option.split("(")[0]).strip() not in plain(request):
            return [f"document.querySelector({json.dumps(selector)}).selectedIndex > 0"], "any_option"
    return [check], None


def relax_task(task: dict, kinds: dict[str, str]) -> tuple[dict, list[str]]:
    """The task with its checks loosened by the rules, and the names of the rules applied."""
    checks, rules = [], []
    for check in task.get("checks", []):
        new, rule = relax_check(check, task.get("request", ""), kinds)
        checks += [c for c in new if c not in checks]
        if rule:
            rules.append(rule)
    return {**task, "checks": checks}, rules


def field_kinds(task: dict, browser) -> dict[str, str]:
    """Each filled or chosen field's kind on the task's page: textarea, select, or the input's type."""
    from eval.plan_run import FIXTURES
    selectors = []
    for check in task.get("checks", []):
        m = FILL.match(check) or SELECT.match(check)
        if m:
            selectors.append(js_string(m.group(1)))
    if not selectors:
        return {}
    page = browser.new_page()
    page.goto((FIXTURES / task["fixture"]).as_uri())
    kinds = page.evaluate("""(sels) => Object.fromEntries(sels.map(s => {
        const e = document.querySelector(s);
        return [s, !e ? 'text' : e.tagName === 'TEXTAREA' ? 'textarea' : e.tagName === 'SELECT' ? 'select'
                   : (e.getAttribute('type') || 'text').toLowerCase()];
    }))""", selectors)
    page.close()
    return kinds


def indentation(text: str) -> int:
    """The file's own indentation (the recorder writes 1 space, the synthetic set has 2), so a rewrite changes
    only the tasks it loosens and the history shows just those."""
    second = text.splitlines()[1] if len(text.splitlines()) > 1 else ""
    return (len(second) - len(second.lstrip(" "))) or 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.relax_checks", description="Loosens the recorder's checks by fixed rules.")
    ap.add_argument("file", type=Path)
    ap.add_argument("--write", action="store_true", help="apply the changes (without it, only shows them)")
    args = ap.parse_args(argv)
    text = args.file.read_text(encoding="utf-8")
    data = json.loads(text)
    indent = indentation(text)
    from playwright.sync_api import sync_playwright
    changed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i, task in enumerate(data["tasks"]):
            if not task.get("reference") or task.get("expected") == "not_possible":
                continue
            new, rules = relax_task(task, field_kinds(task, browser))
            if rules:
                changed += 1
                print(f"{task['id']}: {', '.join(rules)}")
                data["tasks"][i] = new
        browser.close()
    print(f"{changed} task(s) {'changed' if args.write else 'would change'} in {args.file.name}")
    if args.write and changed:
        args.file.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
