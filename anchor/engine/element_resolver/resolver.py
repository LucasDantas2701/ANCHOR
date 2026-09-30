from typing import Callable

from playwright.sync_api import Page

from .loader import load_index_script
from .match import Match
from .scoring import score_element
from .tokenizer import (
    ACTION_WORDS_N,
    build_synonyms,
    extract_object_tokens,
    normalize_text,
    normalize_tokens,
    tokenize,
)

_NOT_TEXT_INPUTS = {"checkbox", "radio", "button", "submit", "reset", "file",
                    "image", "range", "color", "hidden"}


def accepts(record: dict, action: str | None) -> bool:
    """
    O elemento pode receber a ação? Evita, por exemplo, tentar preencher um botão.

        fill:   campos de texto (input de texto, textarea, editáveis)
        select: listas nativas (<select>)
        check:  caixas de marcação, opções e chaves
    """
    tag, role = record.get("tag", ""), record.get("role", "")
    kind = (record.get("type") or "").lower()
    if action == "fill":
        return (tag == "textarea"
                or (tag == "input" and kind not in _NOT_TEXT_INPUTS)
                or (tag != "input" and role in ("textbox", "searchbox")))
    if action == "select":
        return tag == "select"
    if action == "check":
        return ((tag == "input" and kind in ("checkbox", "radio"))
                or role in ("checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio"))
    return True


def merge_nested(matches: list[Match], records: list[dict]) -> list[Match]:
    """
    Une elementos aninhados que são o mesmo alvo: quando um contém o outro e só
    um deles é interativo (ex.: um link e o nome do produto dentro dele), fica o
    interativo, com o maior score dos dois. Se os dois forem interativos (ex.: um
    card clicável com um botão dentro), continuam candidatos distintos.
    """
    by_id = {r["id"]: r for r in records}
    candidates = {m.id: m for m in matches}
    dropped: set[str] = set()

    for match in matches:
        record = by_id.get(match.id, {})
        parent_id = record.get("parentId")
        if not parent_id or parent_id not in candidates:
            continue
        parent = by_id[parent_id]
        if record.get("interactive") == parent.get("interactive"):
            continue
        keep, drop = (parent_id, match.id) if parent.get("interactive") else (match.id, parent_id)
        if drop in dropped or keep in dropped:
            continue
        candidates[keep].score = max(candidates[keep].score, candidates[drop].score)
        dropped.add(drop)

    return [m for m in matches if m.id not in dropped]


class ElementResolver:
    """
    Localiza elementos de uma página utilizando
    descrição em linguagem natural.

    Fluxo:

        página
          ↓
        index()
          ↓
        candidatos
          ↓
        contexto
          ↓
        query()
          ↓
        ranking
          ↓
        Match
    """

    def __init__(
        self,
        page: Page,
        include_hidden: bool = False,
        context_selectors: list[str] | None = None,
        selector: str | None = None,
        synonyms: dict[str, str] | None = None,
    ):
        """
        context_selectors:
            Containers específicos de um site para o contexto
            (ex.: [".inventory_item"]). Opcional: o script já
            tem uma heurística genérica.

        selector:
            Seletor CSS fixo. Se informado, desliga a detecção
            automática do script (use só para depuração).

        synonyms:
            Vocabulário específico do site ou da automação salva
            (ex.: {"mochila": "backpack"}). Soma-se ao dicionário
            genérico, sem precisar alterar o constants.py.
        """

        self.page = page
        self.include_hidden = include_hidden
        self.context_selectors = context_selectors or []
        self.selector = selector
        self._script = load_index_script()
        self._records: list[dict] = []
        self._synonyms = build_synonyms(synonyms or {})

    def index(self, mode: str = "interactive") -> int:
        """
        Analisa a página e cria o índice de elementos.

        mode:
            "interactive": só elementos clicáveis/preenchíveis.
            "content": interativos + elementos com texto (extração).
        """

        self._records = self.page.evaluate(
            self._script,
            {
                "mode": mode,
                "selector": self.selector,
                "includeHidden": self.include_hidden,
                "contextSelectors": self.context_selectors,
            },
        )

        return len(self._records)

    @property
    def records(self) -> list[dict]:
        """Registros da última indexação (um por elemento)."""
        return self._records

    def to_match(self, record: dict, score: float = 0.0) -> Match:
        """Converte um registro do index_script.js em Match."""
        return Match(
            id=record["id"],
            tag=record["tag"],
            role=record["role"],
            label=record["label"],
            text=record["text"],
            content=record["content"],
            context=record["context"],
            rect=record["rect"],
            score=score,
            page=self.page,
            type=record.get("type", ""),
            value=record.get("value", ""),
            hint=record.get("hint", ""),
            href=record.get("href", ""),
            test_id=record.get("testId", ""),
            state=record.get("state", {}),
            options=record.get("options", []),
            in_viewport=record.get("inViewport", True),
            obscured=record.get("obscured", False),
            layer=record.get("layer", False),
        )

    def query(
        self,
        description: str,
        k: int = 5,
        threshold: float = 0.0,
        action: str | None = None,
        filter: Callable[[Match], bool] | None = None,
    ) -> list[Match]:
        """
        Procura elementos relacionados à descrição
        e retorna os melhores candidatos.

        action:
            click
            fill
            extract

        filter:
            Função opcional para filtrar candidatos.
        """

        # Reindexa a cada consulta: a página pode ter mudado
        # desde a última (navegação, re-render). Corrige o B2.
        self.index(
            "content" if action == "extract" else "interactive"
        )

        query = normalize_text(description).strip()

        query_tokens = tokenize(query)

        normalized_query_tokens = normalize_tokens(
            query_tokens,
            self._synonyms,
        )

        # Palavras de ação presentes na consulta.
        action_query_tokens = (
            normalized_query_tokens & ACTION_WORDS_N
            if action
            else set()
        )

        # Objetos relevantes da consulta.
        object_query_tokens = (
            extract_object_tokens(
                normalized_query_tokens,
                action_query_tokens,
            )
            if action
            else normalized_query_tokens
        )

        matches = []

        for record in self._records:

            if not accepts(record, action):
                continue

            content = record["content"]
            value = (record.get("value") or "").lower()
            if value and action not in ("fill", "extract") and accepts(record, "fill"):
                # Para clicar ou marcar, o que identifica um campo é o rótulo, não o
                # texto que já foi digitado nele.
                content = " ".join(content.replace(value, " ").split())

            score = score_element(
                content=content,
                context=record["context"],
                query=query,
                query_tokens=query_tokens,
                normalized_query_tokens=normalized_query_tokens,
                action_query_tokens=action_query_tokens,
                object_query_tokens=object_query_tokens,
                role=record["role"],
                tag=record["tag"],
                action=action,
                text=record["text"],
                synonyms=self._synonyms,
                state=record.get("state"),
                element_text=" ".join(
                    record.get(key) or ""
                    for key in ("label", "text", "hint")
                ),
            )

            match = self.to_match(record, score)

            matches.append(match)

        if filter:
            matches = [
                match
                for match in matches
                if filter(match)
            ]

        matches = merge_nested(matches, self._records)

        matches = [
            match
            for match in matches
            if match.score >= threshold
        ]

        matches.sort(
            key=lambda match: match.score,
            reverse=True,
        )

        return matches[:k]