"""
Parameters of a saved automation: the parts of the request that change from run to run.

They go in braces in the request: "cadastre {nome}, CPF {cpf}, no TI e salve". The model
plans with the real values (it needs them to plan well); the approved plan is saved with
the placeholders back in place of the values ("fill CPF = {cpf}"), so it works for any
value; and each replay fills the placeholders with the values of that run.
"""

from __future__ import annotations

import csv
import re
from dataclasses import replace
from pathlib import Path

from anchor.planner import Step

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ParameterError(ValueError):
    """Missing, unknown or empty parameter values."""


def find_parameters(text: str) -> list[str]:
    """The placeholders of a request, in order, without repetitions."""
    seen: list[str] = []
    for name in PLACEHOLDER.findall(text or ""):
        if name not in seen:
            seen.append(name)
    return seen


def check_values(required: list[str], values: dict[str, str]) -> None:
    missing = [n for n in required if not str(values.get(n, "")).strip()]
    unknown = [n for n in values if n not in required]
    if missing:
        raise ParameterError(f"missing value for: {', '.join(missing)}")
    if unknown:
        raise ParameterError(f"unknown parameter: {', '.join(unknown)} (this automation has: "
                             f"{', '.join(required) or 'none'})")


def render(text, values: dict[str, str]):
    """Fills the placeholders of a text (None stays None)."""
    if text is None:
        return None
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)


def render_steps(steps: list[Step], values: dict[str, str]) -> list[Step]:
    return [replace(s, description=render(s.description, values), value=render(s.value, values),
                    expect=render(s.expect, values)) for s in steps]


def templatize(text, values: dict[str, str]):
    """Puts the placeholders back in place of the values (the longest values first)."""
    if text is None:
        return None
    for name, value in sorted(values.items(), key=lambda kv: -len(str(kv[1]))):
        value = str(value)
        if len(value) >= 2:
            text = text.replace(value, "{" + name + "}")
    return text


def templatize_steps(steps: list[Step], values: dict[str, str]) -> list[Step]:
    if not values:
        return list(steps)
    return [replace(s, description=templatize(s.description, values), value=templatize(s.value, values),
                    expect=templatize(s.expect, values)) for s in steps]


def parse_assignments(items: list[str]) -> dict[str, str]:
    """["nome=Maria Silva", "cpf=123"] → {"nome": "Maria Silva", "cpf": "123"}."""
    values = {}
    for item in items or []:
        if "=" not in item:
            raise ParameterError(f"use name=value, not {item!r}")
        name, value = item.split("=", 1)
        values[name.strip()] = value
    return values


def read_rows(path: str | Path) -> list[dict[str, str]]:
    """The rows of a CSV file, one dict per row (the header gives the names). Accepts the
    separator Excel uses in Brazil (;) as well as the comma."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0] if text else ",", delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    return [{k.strip(): (v or "").strip() for k, v in row.items() if k is not None} for row in rows]
