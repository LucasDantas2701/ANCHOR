"""
A short list of the page's elements, so the planner uses the real names.

The list is sorted by relevance, because on large pages it gets cut:

    1. elements in an open pop-up, dialog or menu (marked with [pop-up]);
    2. elements sharing words with the request (e.g. "pesquise" → "Search");
    3. elements visible on the screen;
    4. the rest of the page.

Elements covered by a pop-up are left out: the user cannot see them and the
agent cannot use them while the pop-up is open.

The summary goes to the model, so it is written in the planner prompt's
language (Portuguese by default), not in the interface language.
"""

from __future__ import annotations

from collections import Counter

from anchor.engine.disambiguation.describe import describe
from anchor.engine.element_resolver import ElementResolver
from anchor.engine.element_resolver.tokenizer import (
    STOPWORDS_N,
    STRUCTURAL_WORDS_N,
    normalize_tokens,
    tokenize,
)
from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, mt
from anchor.planner.untrusted import looks_like_instruction, without_instructions

POPUP_MARK = "[pop-up]"


def _words(text: str) -> set[str]:
    tokens = tokenize(text or "")
    return (tokens | normalize_tokens(tokens)) - STOPWORDS_N - STRUCTURAL_WORDS_N


def page_elements(resolver: ElementResolver, limit: int = 80, request: str | None = None,
                  language: str = DEFAULT_PROMPT_LANGUAGE) -> list[str]:
    resolver.index("interactive")
    records = [r for r in resolver.records if not r.get("obscured")]
    wanted = _words(request) if request else set()

    def priority(record: dict) -> int:
        if record.get("layer"):
            return 0
        if wanted and wanted & _words(record.get("content", "") + " " + record.get("context", "")[:80]):
            return 1
        if record.get("inViewport", True):
            return 2
        return 3

    records.sort(key=priority)  # stable sort: keeps the page order within each group

    # Element kinds in the planner prompt's language.
    views = [describe(resolver.to_match(r), 0, language=language) for r in records]
    repeated = Counter((v.kind, v.name) for v in views)

    lines, seen = [], set()
    for record, v in zip(records, views):
        name, near = _safe_name(v.name, record, language), without_instructions(v.near or "")
        line = f'{v.kind} "{name}"'
        # Dropdowns carry their options: the model needs the exact text.
        if record.get("options"):
            line += mt("summary.options", language, options=" | ".join(record["options"][:10]))
        # Repeated names (e.g. several "Add to cart") carry the surrounding text.
        if repeated[(v.kind, v.name)] > 1 and near:
            line += f" ({near[:40]})"
        if record.get("layer"):
            line += f" {POPUP_MARK}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines + _tables(resolver, language)


def _tables(resolver: ElementResolver, language: str, limit: int = 6) -> list[str]:
    """
    One line per table or list on the page, at the end, so the planner can name them in
    extract_table. Pages without tables get nothing here, and their summary does not change.
    Names come from the page, so the ones that look like instructions are left out.
    """
    from anchor.engine.tables import find_tables
    try:
        tables = find_tables(resolver.page)
    except Exception:
        return []
    out = []
    for t in tables[:limit]:
        name = t.label()
        if not name or looks_like_instruction(name):
            name = mt("summary.untitled", language)
        name = without_instructions(name)[:60]
        if t.kind == "list":
            out.append(mt("summary.list", language, name=name, rows=len(t.rows)))
        else:
            columns = " | ".join(c for c in t.columns[:8] if not looks_like_instruction(c))
            out.append(mt("summary.table", language, name=name, columns=columns, rows=len(t.rows)))
    return out


def _safe_name(name: str, record: dict, language: str) -> str:
    """
    The element's name, unless it looks like an instruction to the assistant (page content
    is data, not orders). A button whose aria-label is an instruction but whose visible text
    is ordinary ("Assinar") keeps the visible text; otherwise, the name is left out.
    """
    if not looks_like_instruction(name):
        return name
    visible = " ".join((record.get("text") or "").split())
    if visible and not looks_like_instruction(visible):
        return visible
    return mt("summary.suspicious", language)
