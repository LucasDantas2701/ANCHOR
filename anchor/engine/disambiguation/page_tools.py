"""
Ferramentas de página para o desempate: destacar candidatos e capturar
o clique do usuário. Tudo opera sobre os atributos data-er-id que o
index_script.js já grava nos elementos.
"""

from __future__ import annotations

from typing import Optional

from playwright.sync_api import Page

from anchor.engine.element_resolver import Match

_HIGHLIGHT_JS = """
(items) => {
    const STYLE_ID = "er-highlight-style";
    if (!document.getElementById(STYLE_ID)) {
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            [data-er-highlight] { outline: 3px solid #e91e63 !important; outline-offset: 2px !important; }
            .er-badge { position: absolute; z-index: 2147483647; pointer-events: none;
                        background: #e91e63; color: #fff; font: bold 13px/1 sans-serif;
                        padding: 4px 7px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.4); }`;
        document.head.appendChild(style);
    }
    for (const { id, number } of items) {
        const el = document.querySelector(`[data-er-id="${id}"]`);
        if (!el) continue;
        el.setAttribute("data-er-highlight", "");
        const r = el.getBoundingClientRect();
        const badge = document.createElement("div");
        badge.className = "er-badge";
        badge.textContent = number;
        badge.style.left = (r.left + scrollX - 10) + "px";
        badge.style.top = (r.top + scrollY - 12) + "px";
        document.body.appendChild(badge);
    }
    const first = items.length && document.querySelector(`[data-er-id="${items[0].id}"]`);
    if (first) first.scrollIntoView({ block: "center" });
}
"""

_CLEAR_JS = """
() => {
    document.querySelectorAll(".er-badge, #er-point-banner").forEach((b) => b.remove());
    document.querySelectorAll("[data-er-highlight]").forEach((e) => e.removeAttribute("data-er-highlight"));
}
"""

# Espera um clique do usuário e o BLOQUEIA (o site não reage a ele):
# quem executa a ação depois é o Executor, uma única vez.
_CAPTURE_JS = """
(timeoutMs) => new Promise((resolve) => {
    const banner = document.createElement("div");
    banner.id = "er-point-banner";
    banner.textContent = "Clique no elemento que o assistente deve usar";
    banner.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:2147483647;pointer-events:none;" +
        "background:#e91e63;color:#fff;font:bold 15px sans-serif;padding:10px;text-align:center";
    document.body.appendChild(banner);

    const events = ["pointerdown", "mousedown", "pointerup", "mouseup", "click"];
    const block = (ev) => { ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation(); };

    const finish = (value) => {
        events.forEach((t) => document.removeEventListener(t, t === "click" ? onClick : block, true));
        banner.remove();
        resolve(value);
    };

    const onClick = (ev) => {
        block(ev);
        const path = ev.composedPath().filter((n) => n instanceof Element);
        let el = path.find((n) => n.hasAttribute("data-er-id")) || path[0];
        if (!el) return finish(null);
        if (!el.hasAttribute("data-er-id")) el.setAttribute("data-er-id", "el-user-" + Date.now());
        const r = el.getBoundingClientRect();
        finish({
            id: el.getAttribute("data-er-id"),
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute("role") || el.tagName.toLowerCase(),
            label: el.getAttribute("aria-label") || el.getAttribute("title") || "",
            text: (el.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 200),
            rect: { x: r.x, y: r.y, width: r.width, height: r.height },
        });
    };

    events.forEach((t) => document.addEventListener(t, t === "click" ? onClick : block, true));
    setTimeout(() => finish(null), timeoutMs);
})
"""


def highlight_candidates(page: Page, matches: list[Match]) -> None:
    page.evaluate(
        _HIGHLIGHT_JS,
        [{"id": m.id, "number": i} for i, m in enumerate(matches, 1)],
    )


def clear_highlights(page: Page) -> None:
    page.evaluate(_CLEAR_JS)


def capture_click(page: Page, timeout_s: float = 120) -> Optional[Match]:
    """Espera o usuário clicar num elemento da página e devolve um Match para ele."""
    info = page.evaluate(_CAPTURE_JS, int(timeout_s * 1000))
    if not info:
        return None
    return Match(
        id=info["id"],
        tag=info["tag"],
        role=info["role"],
        label=info["label"],
        text=info["text"],
        content="",
        context="",
        rect=info["rect"],
        score=0.0,
        page=page,
    )
