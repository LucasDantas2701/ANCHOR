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
        line = f'{v.kind} "{v.name}"'
        # Dropdowns carry their options: the model needs the exact text.
        if record.get("options"):
            line += mt("summary.options", language, options=" | ".join(record["options"][:10]))
        # Repeated names (e.g. several "Add to cart") carry the surrounding text.
        if repeated[(v.kind, v.name)] > 1 and v.near:
            line += f" ({v.near[:40]})"
        if record.get("layer"):
            line += f" {POPUP_MARK}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines
