"""
Checking the effect of each action (layer 1, no LLM).

An observer on the page counts DOM changes and keeps new messages (errors
such as "CPF inválido", confirmations such as "Cadastro salvo"). In Python,
the agent counts requests, new tabs and downloads. After each step:

fill / select / check: the element's state is checked directly;
click / press:         there is an effect if the URL changed, the DOM changed,
a request went out, a tab opened or a download started;
all:                   a new error message turns the step into a failure.

The error and confirmation word lists cover Portuguese and English pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Page

from anchor.planner.language import Reason

# Changes made by ANCHOR itself (the index, disambiguation highlights) do not count.
OBSERVER_JS = r"""
() => {
    if (window.__er_obs) return true;
    window.__er_mut = 0;
    window.__er_msgs = [];
    const ours = (n) => n.nodeType === 1 && (
        n.id === "er-point-banner" || n.id === "er-highlight-style" ||
        (n.classList && n.classList.contains("er-badge")));
    const ALERT = "[role=alert],[role=status],[aria-live],.toast,.alert,.error,.message,.notification,.feedback";
    const MSG = /erro|inválid|invalid|obrigat|required|falh|failed|incorret|incorrect|não foi possível|sucesso|success|salv|saved|enviad|sent|concluíd|adicionad|added/i;
    const note = (el) => {
        if (!el || el.nodeType !== 1 || ours(el)) return;
        const text = (el.innerText || "").replace(/\s+/g, " ").trim();
        if (text.length < 2 || text.length > 160) return;
        const alertLike = el.closest && el.closest(ALERT);
        if (!alertLike && !MSG.test(text)) return;
        if (window.__er_msgs.length < 50) window.__er_msgs.push(text);
    };
    window.__er_obs = new MutationObserver((records) => {
        for (const r of records) {
            if (r.type === "attributes" && (r.attributeName || "").startsWith("data-er-")) continue;
            if (r.type === "childList") {
                const nodes = [...r.addedNodes, ...r.removedNodes];
                if (nodes.length && nodes.every(ours)) continue;
                r.addedNodes.forEach((n) => note(n.nodeType === 3 ? n.parentElement : n));
            }
            if (r.type === "characterData") note(r.target.parentElement);
            if (r.type === "attributes" && r.attributeName === "hidden" && !r.target.hidden) note(r.target);
            window.__er_mut += 1;
        }
    });
    window.__er_obs.observe(document.documentElement,
        { childList: true, subtree: true, attributes: true, characterData: true });
    return true;
}
"""

ERROR_RE = re.compile(
    r"erro|inválid|invalid|obrigat|required|falh|failed|incorret|incorrect|não foi possível", re.I)


@dataclass
class Snapshot:
    url: str
    mutations: int
    messages: int
    requests: int
    pages: int
    downloads: int


@dataclass
class Effect:
    changed: bool
    new_messages: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [m for m in self.new_messages if ERROR_RE.search(m)]


class EffectWatcher:
    """Counts a page's effect signals throughout the run."""

    IGNORED_RESOURCES = {"image", "stylesheet", "font", "media"}

    def __init__(self, page: Page, settle_ms: int = 400):
        self.page = page
        self.settle_ms = settle_ms
        self.requests = self.pages = self.downloads = 0
        page.on("request", self._on_request)
        page.on("download", lambda _: self._bump("downloads"))
        page.context.on("page", lambda _: self._bump("pages"))

    def _bump(self, name: str) -> None:
        setattr(self, name, getattr(self, name) + 1)

    def _on_request(self, request) -> None:
        if request.resource_type not in self.IGNORED_RESOURCES:
            self.requests += 1

    def _page_counters(self) -> tuple[int, int]:
        try:
            self.page.evaluate(OBSERVER_JS)
            return tuple(self.page.evaluate("() => [window.__er_mut, window.__er_msgs.length]"))
        except Exception:
            return (0, 0)

    def snapshot(self) -> Snapshot:
        mutations, messages = self._page_counters()
        return Snapshot(self.page.url, mutations, messages, self.requests, self.pages, self.downloads)

    def effect_since(self, before: Snapshot) -> Effect:
        try:
            self.page.wait_for_timeout(self.settle_ms)
        except Exception:
            pass
        if self.page.url != before.url:
            return Effect(changed=True)
        mutations, messages = self._page_counters()
        try:
            new = self.page.evaluate(f"() => window.__er_msgs.slice({before.messages})")
        except Exception:
            new = []
        changed = (mutations > before.mutations or self.requests > before.requests
                   or self.pages > before.pages or self.downloads > before.downloads)
        return Effect(changed=changed, new_messages=list(dict.fromkeys(new))[:5])


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def state_problem(action: str, value: str | None, locator) -> Optional[Reason]:
    """The reason, if the element did not end up in the state the action asked for; None if it did."""
    try:
        if action == "fill":
            try:
                actual = locator.input_value()
            except Exception:
                actual = locator.inner_text()
            want, got = " ".join((value or "").split()), " ".join((actual or "").split())
            if got == want or (want and _digits(want) and _digits(want) == _digits(got)) or (want and want in got):
                return None
            return Reason("why.field_value", got=got[:60], want=want[:60])
        if action == "select":
            chosen = locator.evaluate(
                "e => e.selectedOptions && e.selectedOptions[0] ? [e.selectedOptions[0].text, e.value] : ['', '']")
            if any((value or "").strip().lower() == (c or "").strip().lower() for c in chosen):
                return None
            return Reason("why.list_value", got=chosen[0], want=value)
        if action in ("check", "uncheck"):
            checked = locator.is_checked()
            if checked == (action == "check"):
                return None
            return Reason("why.not_checked" if action == "check" else "why.still_checked")
    except Exception:
        return None  # the element disappeared or changed (e.g. navigation): cannot check
    return None
