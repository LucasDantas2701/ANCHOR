from __future__ import annotations

from typing import Any, Callable, Optional

from playwright.sync_api import Page

from app.engine.disambiguation import (
    ChoiceRequest,
    Disambiguator,
    capture_click,
    clear_highlights,
    describe,
    highlight_candidates,
)
from app.engine.element_resolver import ElementResolver, Match
from app.engine.memory import ChoiceMemory

from .constants import (
    DEFAULT_AMBIGUITY_GAP,
    DEFAULT_K,
    DEFAULT_MIN_SCORE,
    RESOLVER_ACTION_MAP,
)
from .result import ActionResult


class ActionExecutor:
    """
    Orquestra ElementResolver + execução de ações no Playwright.

    Fluxo:

        descrição
            ↓
        ElementResolver
            ↓
        candidatos
            ↓
        score mínimo
            ↓
        verificação de ambiguidade
            ↓
        elemento selecionado
            ↓
        execução
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
    ):
        """
        disambiguator:
            Quem pergunta ao usuário quando a heurística recusa
            (ambiguous / not_found). Sem ele, o Executor devolve a
            recusa, como antes.

        can_point:
            True quando o navegador está visível (headed): o usuário
            pode clicar direto no elemento.

        memory:
            Memória das escolhas do usuário. Com ela, um passo que já foi
            desempatado antes é resolvido direto, sem perguntar de novo.
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

        # Margem relativa ao score do 1º colocado (ver constants.py).
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

        # 1. Memória: o usuário já escolheu este elemento antes?
        if self.memory is not None:
            found = self._from_memory(url, description, action_name, resolver_action)

            if found is not None:
                remembered, similarity = found
                try:
                    value = fn(remembered)
                except Exception as exc:
                    # A escolha antiga não serve mais: esquece.
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

        # 2. Heurística (e, se ela recusar, o usuário).
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

        # Assinatura capturada ANTES da ação (ela pode mudar ou sair da página).
        to_remember = (
            self._signature_of(match)
            if resolved_by == "user" and self.memory is not None
            else None
        )

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

        # 3. Deu certo com a escolha do usuário: guarda para a próxima vez.
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
    # Memória
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
        """Assinatura do elemento (pelo registro completo, quando existir) + caminho CSS."""
        record = next((r for r in self.resolver.records if r["id"] == match.id), None)
        if record:
            signature = {**record, "test_id": record.get("testId", "")}
        else:  # elemento capturado por clique, fora do índice
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
        """Elemento memorizado na página atual, com a similaridade (0 = só pelo caminho CSS)."""
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
        """Plano B: o caminho CSS salvo, conferindo se o elemento ainda é o mesmo."""
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
        Mostra só o que vale a pena ao usuário:

        ambiguous: os candidatos com score perto do 1º (>= choice_ratio
                   do score dele), no mínimo 2 e no máximo max_choices.
        not_found: no máximo 3, porque o mais provável é o alvo nem estar
                   na lista (o usuário deve clicar direto na página).
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
        """Desempate: destaca os candidatos, pergunta e devolve a escolha."""

        shown = self._choices_to_show(reason, candidates)

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
            return shown[choice.number - 1]

        if choice.kind == "point" and self.can_point:
            self.disambiguator.notify(
                "Clique no elemento na janela do navegador."
            )
            captured = capture_click(self.page, self.point_timeout_s)
            return self._enrich_captured(captured, action_name) if captured else None

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
        O elemento clicado pelo usuário, com a assinatura completa (contexto,
        pista visual, data-testid), para a memória reencontrá-lo depois.
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