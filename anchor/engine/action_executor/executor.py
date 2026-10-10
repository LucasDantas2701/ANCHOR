from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.sync_api import Page

from anchor.engine.disambiguation import (
    ChoiceRequest,
    Disambiguator,
    capture_click,
    clear_highlights,
    describe,
    highlight_candidates,
)
from anchor.engine.element_resolver import ElementResolver, Match
from anchor.engine.memory import ChoiceMemory

from .constants import (
    DEFAULT_AMBIGUITY_GAP,
    DEFAULT_K,
    DEFAULT_MIN_SCORE,
    RESOLVER_ACTION_MAP,
)
from .result import ActionResult

_NO_DOWNLOAD = object()


def _free_path(folder: Path, name: str) -> Path:
    """folder/name, or folder/name (2), (3)... if taken: a download never overwrites a file."""
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(name).name or "download"
    path, stem, suffix, n = folder / name, Path(name).stem, Path(name).suffix, 2
    while path.exists():
        path, n = folder / f"{stem} ({n}){suffix}", n + 1
    return path

class ActionExecutor:
    """
    Orchestrates the ElementResolver + running actions in Playwright.

    Flow:

        description
            ↓
        ElementResolver
            ↓
        candidates
            ↓
        minimum score
            ↓
        ambiguity check
            ↓
        selected element
            ↓
        execution
            ↓
        ActionResult
    """

    def __init__(
        self,
        page: Page,
        resolver: Optional[ElementResolver] = None,
        min_score: float = DEFAULT_MIN_SCORE,
        ambiguity_gap: float = DEFAULT_AMBIGUITY_GAP,
        k: int = DEFAULT_K,
        disambiguator: Optional[Disambiguator] = None,
        can_point: bool = False,
        max_choices: int = 5,
        choice_ratio: float = 0.70,
        point_timeout_s: float = 120,
        memory: Optional[ChoiceMemory] = None,
        confirmer=None,
    ):
        """
        disambiguator:
            Whatever asks the user when the heuristic refuses
            (ambiguous / not_found). Without it, the Executor returns
            the refusal, as before.

        can_point:
            True when the browser is visible (headed): the user
            can click the element directly.

        memory:
            Memory of the user's choices. With it, a step that was already
            disambiguated is resolved directly, without asking again.

        confirmer:
            Whatever asks the user to approve a sensitive action (delete, save,
            send, pay, download, upload), after the element is found and before
            the action. A denied action is not performed (status "denied").
            Without it, nothing is asked.
        """
        self.page = page

        self.resolver = (
            resolver
            if resolver is not None
            else ElementResolver(page)
        )

        self.min_score = min_score
        self.ambiguity_gap = ambiguity_gap
        self.k = k
        self.disambiguator = disambiguator
        self.can_point = can_point
        self.max_choices = max_choices
        self.choice_ratio = choice_ratio
        self.point_timeout_s = point_timeout_s
        self.memory = memory
        self.confirmer = confirmer
        # When True, filling a password field is refused (status "credential") instead of typed:
        # the agent turns it on, so credentials never go through the model and the user logs in
        # by hand. Off by default, for the resolver's evaluation on test pages.
        self.refuse_passwords = False
        # Where download() saves files; the agent points it at its output folder.
        self.download_dir = Path("output")
        # Time spent waiting for the user (disambiguation and confirmations), kept apart so it
        # does not inflate the measured execution time.
        self.user_wait_s = 0.0

    def _resolve(
        self,
        description: str,
        resolver_action: str,
    ) -> tuple[
        str,
        Optional[Match],
        Optional[list[Match]],
    ]:

        matches = self.resolver.query(
            description,
            k=self.k,
            action=resolver_action,
        )

        if (
            not matches
            or matches[0].score < self.min_score
        ):
            return (
                "not_found",
                None,
                matches,
            )

        if len(matches) == 1:
            return (
                "success",
                matches[0],
                matches,
            )

        # Margin relative to the 1st candidate's score (see constants.py).
        gap = (
            matches[0].score
            - matches[1].score
        ) / matches[0].score

        if gap < self.ambiguity_gap:
            return (
                "ambiguous",
                None,
                matches,
            )

        return (
            "success",
            matches[0],
            matches,
        )

    def _run(
        self,
        description: str,
        action_name: str,
        fn: Callable[[Match], Any],
    ) -> ActionResult:

        resolver_action = RESOLVER_ACTION_MAP.get(
            action_name,
            action_name,
        )

        url = self.page.url

        # 1. Memory: has the user chosen this element before?
        if self.memory is not None:
            found = self._from_memory(url, description, action_name, resolver_action)

            if found is not None:
                remembered, similarity = found
                # (ActionResult is falsy unless it succeeded: no "or" here.)
                denied = self._credential(action_name, description, remembered, "memory")
                if denied is None:
                    denied = self._denied(action_name, description, remembered)
                if denied is not None:
                    return denied
                try:
                    value = fn(remembered)
                except Exception as exc:
                    # The old choice no longer works: forget it.
                    self.memory.forget(url, action_name, description)
                    return ActionResult(
                        status="error",
                        action=action_name,
                        description=description,
                        selected_element=remembered,
                        error=str(exc),
                        resolved_by="memory",
                        similarity=similarity,
                    )

                self.memory.mark_used(url, action_name, description)
                return ActionResult(
                    status="success",
                    action=action_name,
                    description=description,
                    selected_element=remembered,
                    value=value,
                    resolved_by="memory",
                    similarity=similarity,
                )

        # 2. Heuristic (and, if it refuses, the user).
        status, match, candidates = self._resolve(
            description,
            resolver_action,
        )

        resolved_by = "heuristic"

        if status in ("not_found", "ambiguous"):

            if self.disambiguator is None:
                return ActionResult(
                    status=status,
                    action=action_name,
                    description=description,
                    candidates=candidates,
                )

            match = self._ask_user(
                description, action_name, status, candidates or []
            )

            if match is None:
                return ActionResult(
                    status=status,
                    action=action_name,
                    description=description,
                    candidates=candidates,
                    resolved_by="user_skipped",
                )

            resolved_by = "user"

        assert match is not None

        # Signature captured BEFORE the action (the element may change or leave the page).
        to_remember = (
            self._signature_of(match)
            if resolved_by == "user" and self.memory is not None
            else None
        )

        # (ActionResult is falsy unless it succeeded: no "or" here.)
        denied = self._credential(action_name, description, match, resolved_by)
        if denied is None:
            denied = self._denied(action_name, description, match, resolved_by)
        if denied is not None:
            return denied

        try:
            value = fn(match)

        except Exception as exc:
            return ActionResult(
                status="error",
                action=action_name,
                description=description,
                selected_element=match,
                score=match.score,
                error=str(exc),
                resolved_by=resolved_by,
            )

        # 3. It worked with the user's choice: keep it for next time.
        if to_remember is not None:
            signature, css_path = to_remember
            self.memory.remember(url, action_name, description, signature, css_path)

        return ActionResult(
            status="success",
            action=action_name,
            description=description,
            selected_element=match,
            score=match.score,
            value=value,
            resolved_by=resolved_by,
        )

    # ------------------------------------------------------------------
    # Sensitive actions
    # ------------------------------------------------------------------

    def _credential(self, action_name: str, description: str, match: Match,
                    resolved_by: str = "heuristic") -> Optional[ActionResult]:
        """A fill that would type into a password field, refused (see refuse_passwords)."""
        if not self.refuse_passwords or action_name != "fill" or (match.type or "").lower() != "password":
            return None
        return ActionResult(status="credential", action=action_name, description=description,
                            selected_element=match, score=match.score, resolved_by=resolved_by)

    def _denied(self, action_name: str, description: str, match: Match,
                resolved_by: str = "memory") -> Optional[ActionResult]:
        """Asks the confirmer about a sensitive action; the refusal, if it was denied."""
        if self.confirmer is None:
            return None
        from anchor.engine.sensitive import ConfirmationRequest, classify

        element = " ".join(x for x in (match.text, match.label, match.hint) if x).strip()
        category = classify(action_name, description, element)
        if category is None:
            return None
        request = ConfirmationRequest(action_name, description, element or description, category, self.page.url)
        waited = time.perf_counter()
        allowed = self.confirmer.confirm(request)
        self.user_wait_s += time.perf_counter() - waited
        if allowed:
            return None
        return ActionResult(status="denied", action=action_name, description=description,
                            selected_element=match, score=match.score, resolved_by=resolved_by)

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    _CSS_PATH_JS = """
    (el) => {
        const unique = (id) => id && document.querySelectorAll("#" + CSS.escape(id)).length === 1;
        const parts = [];
        for (let n = el; n && n.nodeType === 1 && n !== document.body; n = n.parentElement) {
            if (unique(n.id)) { parts.unshift("#" + CSS.escape(n.id)); return parts.join(" > "); }
            let i = 1;
            for (let s = n.previousElementSibling; s; s = s.previousElementSibling) if (s.tagName === n.tagName) i++;
            parts.unshift(n.tagName.toLowerCase() + ":nth-of-type(" + i + ")");
        }
        return "body > " + parts.join(" > ");
    }
    """

    def _signature_of(self, match: Match) -> tuple[dict, str]:
        """The element's signature (from the full record, when there is one) + CSS path."""
        record = next((r for r in self.resolver.records if r["id"] == match.id), None)
        if record:
            signature = {**record, "test_id": record.get("testId", "")}
        else:  # element captured by a click, outside the index
            signature = {
                "role": match.role, "tag": match.tag, "label": match.label,
                "text": match.text, "hint": match.hint, "test_id": match.test_id,
                "context": match.context,
            }
        try:
            css_path = match.locator.evaluate(self._CSS_PATH_JS)
        except Exception:
            css_path = ""
        return signature, css_path

    def _from_memory(
        self,
        url: str,
        description: str,
        action_name: str,
        resolver_action: str,
    ) -> Optional[tuple[Match, float]]:
        """The remembered element on the current page, with its similarity (0 = CSS path only)."""
        entry = self.memory.lookup(url, action_name, description)
        if entry is None:
            return None

        self.resolver.index("content" if resolver_action == "extract" else "interactive")
        found = self.memory.find(entry, self.resolver.records)

        if found.record is not None:
            return self.resolver.to_match(found.record), found.similarity

        if found.css_path:
            match = self._from_css_path(found.css_path, entry.signature)
            if match is not None:
                return match, 0.0

        self.memory.mark_missed(url, action_name, description)
        return None

    def _from_css_path(self, css_path: str, signature: dict) -> Optional[Match]:
        """Plan B: the saved CSS path, checking that the element is still the same."""
        try:
            locator = self.page.locator(css_path)
            if locator.count() != 1 or not locator.is_visible():
                return None
            info = locator.evaluate(
                """(e) => {
                    if (!e.hasAttribute("data-er-id")) e.setAttribute("data-er-id", "el-mem-" + Date.now());
                    return { id: e.getAttribute("data-er-id"), tag: e.tagName.toLowerCase(),
                             text: (e.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 200) };
                }"""
            )
        except Exception:
            return None

        expected = signature.get("text") or ""
        if info["tag"] != signature.get("tag") or (expected and expected != info["text"]):
            return None

        return Match(
            id=info["id"], tag=info["tag"], role=signature.get("role", info["tag"]),
            label=signature.get("label", ""), text=info["text"], content="", context="",
            rect={}, score=0.0, page=self.page,
        )

    def _choices_to_show(
        self,
        reason: str,
        candidates: list[Match],
    ) -> list[Match]:
        """
        Shows the user only what is worth showing:

        ambiguous: candidates whose score is close to the 1st (>= choice_ratio
                   of its score), at least 2 and at most max_choices.
        not_found: at most 3, because the target is most likely not even in
                   the list (the user should click directly on the page).
        """
        if not candidates:
            return []

        if reason == "not_found":
            return [m for m in candidates[:3] if m.score > 0]

        top = candidates[0].score
        close = [m for m in candidates if m.score >= top * self.choice_ratio]
        return candidates[: max(2, min(len(close), self.max_choices))]

    def _ask_user(
        self,
        description: str,
        action_name: str,
        reason: str,
        candidates: list[Match],
    ) -> Optional[Match]:
        """Disambiguation: highlights the candidates, asks, and returns the choice."""

        shown = self._choices_to_show(reason, candidates)
        waited = time.perf_counter()

        try:
            highlight_candidates(self.page, shown)
            screenshot = (
                None if self.can_point
                else self.page.screenshot(full_page=True)
            )
            choice = self.disambiguator.choose(ChoiceRequest(
                action=action_name,
                description=description,
                reason=reason,
                candidates=[describe(m, i) for i, m in enumerate(shown, 1)],
                screenshot=screenshot,
                can_point=self.can_point,
            ))
        finally:
            clear_highlights(self.page)

        if choice.kind == "candidate" and choice.number:
            self.user_wait_s += time.perf_counter() - waited
            return shown[choice.number - 1]

        if choice.kind == "point" and self.can_point:
            self.disambiguator.notify(
                "Clique no elemento na janela do navegador."
            )
            captured = capture_click(self.page, self.point_timeout_s)
            self.user_wait_s += time.perf_counter() - waited
            return self._enrich_captured(captured, action_name) if captured else None

        self.user_wait_s += time.perf_counter() - waited
        return None

    _MARK_PICKED_JS = """(id) => {
        const e = document.querySelector(`[data-er-id="${id}"]`);
        if (e) e.setAttribute("data-er-picked", "1");
        return !!e;
    }"""

    _READ_PICKED_JS = """() => {
        const e = document.querySelector("[data-er-picked]");
        if (!e) return null;
        e.removeAttribute("data-er-picked");
        if (e.hasAttribute("data-er-id")) return { id: e.getAttribute("data-er-id"), indexed: true };
        const id = "el-user-" + Date.now();
        e.setAttribute("data-er-id", id);
        return {
            id, indexed: false,
            context: (e.parentElement && e.parentElement.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 300),
            testId: e.getAttribute("data-testid") || e.getAttribute("data-test") || "",
            label: e.getAttribute("aria-label") || e.getAttribute("title") || "",
        };
    }"""

    def _enrich_captured(self, match: Match, action_name: str) -> Match:
        """
        The element clicked by the user, with its full signature (context,
        visual hint, data-testid), so the memory can find it again later.
        """
        try:
            if not self.page.evaluate(self._MARK_PICKED_JS, match.id):
                return match
            mode = "content" if action_name.startswith("extract") else "interactive"
            self.resolver.index(mode)
            info = self.page.evaluate(self._READ_PICKED_JS)
        except Exception:
            return match
        if not info:
            return match
        if info["indexed"]:
            record = next((r for r in self.resolver.records if r["id"] == info["id"]), None)
            if record is not None:
                return self.resolver.to_match(record)
        match.id = info["id"]
        match.context = info.get("context", "")
        match.test_id = info.get("testId", "")
        match.label = match.label or info.get("label", "")
        return match

    def click(
        self,
        description: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "click",
            lambda match: match.locator.click(
                **kwargs
            ),
        )

    def download(
        self,
        description: str,
        timeout_ms: int = 8000,
    ) -> ActionResult:
        """
        Clicks the button or link the description names and waits for the file it downloads,
        saving it in download_dir with the name the site suggests (never overwriting one).
        value = {"name", "path", "bytes"}. A click that downloads nothing is "no_download".
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        def act(match: Match):
            try:
                with self.page.expect_download(timeout=timeout_ms) as info:
                    match.locator.click()
            except PlaywrightTimeout:
                return _NO_DOWNLOAD
            file = info.value
            path = _free_path(Path(self.download_dir), file.suggested_filename or "download")
            file.save_as(str(path))
            return {"name": path.name, "path": str(path), "bytes": path.stat().st_size}

        result = self._run(description, "download", act)
        if result.status == "success" and result.value is _NO_DOWNLOAD:
            result.status, result.value, result.error = "no_download", None, "the click did not download any file"
        return result

    def hover(
        self,
        description: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "hover",
            lambda match: match.locator.hover(
                **kwargs
            ),
        )

    def check(
        self,
        description: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "check",
            lambda match: match.locator.check(
                **kwargs
            ),
        )

    def uncheck(
        self,
        description: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "uncheck",
            lambda match: match.locator.uncheck(
                **kwargs
            ),
        )

    def press(
        self,
        description: str,
        key: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "press",
            lambda match: match.locator.press(
                key,
                **kwargs,
            ),
        )

    def fill(
        self,
        description: str,
        value: str,
        **kwargs,
    ) -> ActionResult:

        return self._run(
            description,
            "fill",
            lambda match: match.locator.fill(
                value,
                **kwargs,
            ),
        )

    def select(
        self,
        description: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        index: Optional[int] = None,
        **kwargs,
    ) -> ActionResult:

        def _select(match: Match):

            if value is not None:
                return match.locator.select_option(
                    value=value,
                    **kwargs,
                )

            if label is not None:
                return match.locator.select_option(
                    label=label,
                    **kwargs,
                )

            if index is not None:
                return match.locator.select_option(
                    index=index,
                    **kwargs,
                )

            raise ValueError(
                "select() requer value, label ou index"
            )

        return self._run(
            description,
            "select",
            _select,
        )

    def extract_text(
        self,
        description: str,
    ) -> ActionResult:

        return self._run(
            description,
            "extract_text",
            lambda match: match.locator.inner_text(),
        )

    def extract_table(
        self,
        description: str,
    ) -> ActionResult:
        """
        Reads the table or list the description names (by its caption, title or column
        headers), whole. value = the TableData. With several that could be it, refuses
        ("ambiguous") and error lists their names, so the planner can pick one.
        """
        from anchor.engine.tables import find_tables, match_table

        tables = find_tables(self.page)
        table, candidates = match_table(tables, description)
        if table is not None:
            return ActionResult(status="success", action="extract_table", description=description, value=table)
        if not tables:
            return ActionResult(status="not_found", action="extract_table", description=description,
                                error="no table or list on the page")
        names = [t.label() for t in candidates[:6]]
        return ActionResult(status="ambiguous", action="extract_table", description=description,
                            value=names, error="more than one table or list could be it: "
                            + ", ".join(f'"{n}"' for n in names))

    def extract_attribute(
        self,
        description: str,
        attribute: str,
    ) -> ActionResult:

        return self._run(
            description,
            "extract_attribute",
            lambda match: match.locator.get_attribute(
                attribute
            ),
        )

    def extract_value(
        self,
        description: str,
    ) -> ActionResult:

        return self._run(
            description,
            "extract_value",
            lambda match: match.locator.input_value(),
        )