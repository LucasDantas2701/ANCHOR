"""
The documents of a page: the page itself first, then its iframes (attached ones only).

Everything that reads the page goes through each of them, so elements, effects, tables, value
texts and password fields inside an iframe are seen too. A page with no iframes is read exactly as
before.
"""

from __future__ import annotations


def documents(page) -> list:
    """The page's main frame, then each attached iframe."""
    try:
        frames = page.frames
    except Exception:
        return [page]
    out = [page]
    for frame in frames[1:]:
        try:
            if not frame.is_detached():
                out.append(frame)
        except Exception:
            continue
    return out


def evaluate_all(page, script, arg=None) -> list:
    """The script's result in each document (documents that fail are left out)."""
    results = []
    for doc in documents(page):
        try:
            results.append(doc.evaluate(script, arg) if arg is not None else doc.evaluate(script))
        except Exception:
            continue
    return results
