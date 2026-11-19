"""
Two baselines for element selection, with no model (decided on 19/11/2026, before the final run), measured on
the Resolver's closed set with the same metrics as Table 7 (python -m eval.run --baseline exact|bm25).

Both rank the very elements the Resolver indexes on the same page (ElementResolver.index, in the mode the
executor uses for the action), so only the ranking differs:

  exact   the element's accessible name (its label, which holds aria-label, or else its text, value or hint)
          equals the step's description, both normalised (lowercase, no accents, letters and digits only). As the
          descriptions start with a word such as "button" or "field", the description also counts without
          that first word (and a "de"/"do"/"da"/"of" after it). Matches keep the page's order.
  bm25    Okapi BM25 (k1 = 1.2, b = 0.75) of the description against each element's name, hints (hint,
          data-testid) and context, the words only normalised (lowercase, no accents): none of the Resolver's
          compound phrases, stems or glossary, so it knows none of its language.

Each acts on its first element when it has one with a score, and refuses otherwise (not found).
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

BASELINES = ("exact", "bm25")
ROLE_WORDS = {"botao", "campo", "link", "lista", "caixa", "opcao", "aba", "menu", "icone", "texto", "tabela", "secao",
              "area", "cartao", "coluna", "linha", "seletor", "button", "field", "list", "box", "option", "tab",
              "icon", "text", "table", "section", "card", "column", "row", "checkbox", "dropdown", "selector"}
LINKS = {"de", "do", "da", "dos", "das", "of", "the"}
K1, B = 1.2, 0.75


def words(text: str) -> list[str]:
    """Lowercase, no accents, letters and digits only: none of the Resolver's normalisation (its compound
    phrases, stems and glossary are knowledge of its own, which a baseline must not have)."""
    plain = unicodedata.normalize("NFKD", (text or "").lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", plain)


def name_of(record: dict) -> str:
    return next((record.get(f) for f in ("label", "text", "value", "hint") if (record.get(f) or "").strip()), "")


def query_forms(description: str) -> set[str]:
    """The description, and the description without its first word when that word names a kind of element."""
    w = words(description)
    forms = {" ".join(w)}
    if len(w) > 1 and w[0] in ROLE_WORDS:
        rest = w[1:]
        if len(rest) > 1 and rest[0] in LINKS:
            rest = rest[1:]
        forms.add(" ".join(rest))
    return forms


def rank_exact(description: str, records: list[dict]) -> list[tuple[dict, float]]:
    forms = query_forms(description)
    return [(r, 1.0) for r in records if " ".join(words(name_of(r))) in forms]


def document(record: dict) -> list[str]:
    return words(" ".join([name_of(record), record.get("hint") or "", record.get("testId") or "",
                           record.get("context") or ""]))


def rank_bm25(description: str, records: list[dict]) -> list[tuple[dict, float]]:
    docs = [document(r) for r in records]
    n = len(docs)
    if not n:
        return []
    avg = sum(len(d) for d in docs) / n or 1.0
    df = Counter(w for d in docs for w in set(d))
    query = words(description)
    scored = []
    for record, d in zip(records, docs):
        tf = Counter(d)
        score = 0.0
        for w in query:
            if tf[w]:
                idf = math.log((n - df[w] + 0.5) / (df[w] + 0.5) + 1)
                score += idf * tf[w] * (K1 + 1) / (tf[w] + K1 * (1 - B + B * len(d) / avg))
        if score > 0:
            scored.append((record, score))
    return sorted(scored, key=lambda pair: -pair[1])          # stable: ties keep the page's order


def rank(baseline: str, description: str, records: list[dict]) -> list[tuple[dict, float]]:
    return {"exact": rank_exact, "bm25": rank_bm25}[baseline](description, records)
