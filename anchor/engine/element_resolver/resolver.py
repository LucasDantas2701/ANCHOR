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
    Can the element receive the action? Prevents, for example, filling a button.

        fill:   text fields (text inputs, textareas, editable elements)
        select: native lists (<select>)
        check:  checkboxes, radio buttons and switches
        extract (text): anything except checkboxes, radio buttons and switches,
                        which have no text to extract (only a state)
    """
    tag, role = record.get("tag", ""), record.get("role", "")
    kind = (record.get("type") or "").lower()
    if action == "fill":
        return (tag == "textarea"
                or (tag == "input" and kind not in _NOT_TEXT_INPUTS)
                or (tag != "input" and role in ("textbox", "searchbox")))
    if action == "select":
        return tag == "select"
    is_toggle = ((tag == "input" and kind in ("checkbox", "radio"))
                 or role in ("checkbox", "radio", "switch", "menuitemcheckbox", "menuitemradio"))
    if action == "check":
        return is_toggle
    if action == "extract":
        return not is_toggle
    return True


def merge_nested(matches: list[Match], records: list[dict]) -> list[Match]:
    """
    Merges nested elements that are the same target: when one contains the other
    and only one of them is interactive (e.g. a link and the product name inside
    it), the interactive one is kept, with the higher score of the two. If both are
    interactive (e.g. a clickable card with a button inside), they remain separate
    candidates.
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
    Finds elements on a page from a natural-language
    description.

    Flow:

        page
          ↓
        index()
          ↓
        candidates
          ↓
        context
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
            Site-specific containers used for context
            (e.g. [".inventory_item"]). Optional: the script already
            has a generic heuristic.

        selector:
            Fixed CSS selector. When given, it turns off the script's
            automatic detection (use it only for debugging).

        synonyms:
            Vocabulary specific to the site or to the saved automation
            (e.g. {"mochila": "backpack"}). It is added to the generic
            dictionary, with no need to change constants.py.
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
        Scans the page and builds the element index.

        mode:
            "interactive": only clickable/fillable elements.
            "content": interactive elements + elements with text (extraction).
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
        """Records from the last indexing (one per element)."""
        return self._records

    def to_match(self, record: dict, score: float = 0.0) -> Match:
        """Converts a record from index_script.js into a Match."""
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
        Looks for elements related to the description
        and returns the best candidates.

        action:
            click
            fill
            extract

        filter:
            Optional function to filter candidates.
        """

        # Reindex on every query: the page may have changed
        # since the last one (navigation, re-render). Fixes bug B2.
        self.index(
            "content" if action == "extract" else "interactive"
        )

        query = normalize_text(description).strip()

        query_tokens = tokenize(query)

        normalized_query_tokens = normalize_tokens(
            query_tokens,
            self._synonyms,
        )

        # Action words present in the query.
        action_query_tokens = (
            normalized_query_tokens & ACTION_WORDS_N
            if action
            else set()
        )

        # Relevant objects in the query.
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
                # To click or check, a field is identified by its label, not by
                # the text already typed into it.
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