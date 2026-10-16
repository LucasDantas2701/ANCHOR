"""
Cookie banners: declined, never accepted, when they are in the way.

A cookie or consent banner covering the page blocks the step (and the "Show more" that may hide its
target). The agent closes it with the most restrictive option the banner offers ("Recusar",
"Reject all", "Only essential"), reports it, and goes on. A banner with no such option is left alone:
the agent never accepts cookies on its own. Other layers (a promotion, a notice) are not touched.
"""

from __future__ import annotations

from typing import Optional

from anchor.engine.frames import documents

_FIND_JS = r"""
() => {
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const ABOUT = /\b(cookies?|consentimento|consent|lgpd|gdpr|rastreamento|tracking)\b/i;
  const DECLINE = /^\s*(recusar(\s+todos?)?|rejeitar(\s+todos?)?|n[aã]o\s+aceito|decline(\s+all)?|reject(\s+all)?|deny|refuse|s[oó]\s+(os\s+)?essenciais|apenas\s+(os\s+)?necess[aá]rios|only\s+(essential|necessary)|necessary\s+only|essential\s+only)\s*$/i;
  for (const box of document.querySelectorAll('[role=dialog], [role=alertdialog], [aria-modal=true], div, section, aside')) {
    if (!visible(box)) continue;
    const style = getComputedStyle(box);
    const layer = box.matches('[role=dialog], [role=alertdialog], [aria-modal=true]') || style.position === 'fixed' || style.position === 'sticky';
    if (!layer || !ABOUT.test(box.innerText || '') || (box.innerText || '').length > 1500) continue;
    const button = [...box.querySelectorAll('button, a, [role=button], input[type=button], input[type=submit]')]
      .find((b) => visible(b) && DECLINE.test(b.innerText || b.value || b.getAttribute('aria-label') || ''));
    if (button) { button.setAttribute('data-anchor-decline', '1'); return (button.innerText || button.value || '').trim(); }
  }
  return null;
}
"""


def decline_cookies(page) -> Optional[str]:
    """Clicks the decline option of a cookie banner on the page (or in an iframe); its text, or None."""
    for doc in documents(page):
        try:
            label = doc.evaluate(_FIND_JS)
        except Exception:
            continue
        if not label:
            continue
        try:
            doc.locator("[data-anchor-decline]").first.click(timeout=3000)
            return label
        except Exception:
            return None
    return None
