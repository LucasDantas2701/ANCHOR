"""
Lista curta dos elementos da página, para o planejador usar os nomes reais.

A lista é ordenada por relevância, porque em páginas grandes ela é cortada:

    1. elementos num pop-up, diálogo ou menu aberto (marcados com [pop-up]);
    2. elementos com palavras em comum com o pedido (ex.: "pesquise" → "Search");
    3. elementos visíveis na tela;
    4. o restante da página.

Elementos cobertos por um pop-up ficam de fora: o usuário não os vê e o
agente não consegue usá-los enquanto o pop-up estiver aberto.
"""

from __future__ import annotations

from collections import Counter

from app.engine.disambiguation.describe import describe
from app.engine.element_resolver import ElementResolver
from app.engine.element_resolver.tokenizer import (
    STOPWORDS_N,
    STRUCTURAL_WORDS_N,
    normalize_tokens,
    tokenize,
)

POPUP_MARK = "[pop-up]"


def _words(text: str) -> set[str]:
    tokens = tokenize(text or "")
    return (tokens | normalize_tokens(tokens)) - STOPWORDS_N - STRUCTURAL_WORDS_N


def page_elements(resolver: ElementResolver, limit: int = 80, request: str | None = None) -> list[str]:
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

    records.sort(key=priority)  # ordenação estável: mantém a ordem da página em cada grupo

    views = [describe(resolver.to_match(r), 0) for r in records]
    repeated = Counter((v.kind, v.name) for v in views)

    lines, seen = [], set()
    for record, v in zip(records, views):
        line = f'{v.kind} "{v.name}"'
        # Listas de opções levam as opções: o modelo precisa do texto exato.
        if record.get("options"):
            line += " [opções: " + " | ".join(record["options"][:10]) + "]"
        # Nomes repetidos (ex.: vários "Add to cart") levam o texto ao redor.
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
