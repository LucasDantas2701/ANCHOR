"""
How the interface opens the browser, in one place.

- "headless": no window at all; only the automated tests use it.
- "offscreen": a real browser window, placed outside the screen. The person watches it through the
  interface's live view; sites see an ordinary browser (a headless one says "HeadlessChrome" in its
  user agent, which some sites block). The flags keep an unseen window drawing and its timers running.
- "window": a real window on the screen, when the person asks to see the browser.

The window is 1366 x 768, with the site's notifications turned off. The language and the time zone
are not set: a browser with a window takes the system's (Windows's) own.
"""
from __future__ import annotations

SIZE = {"width": 1366, "height": 768}
COMMON = ["--disable-notifications", f"--window-size={SIZE['width']},{SIZE['height']}"]
OFFSCREEN = ["--window-position=-32000,-32000", "--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding", "--disable-background-timer-throttling"]
MODES = ("headless", "offscreen", "window")


def launch_options(mode: str) -> dict:
    """The keyword arguments of chromium.launch (or launch_persistent_context) for a mode."""
    if mode not in MODES:
        raise ValueError(f"unknown browser mode: {mode}")
    if mode == "headless":
        return {"headless": True}
    return {"headless": False, "args": COMMON + (OFFSCREEN if mode == "offscreen" else [])}


def context_options() -> dict:
    """The keyword arguments of a browser context: the page's size (the language and time zone: the system's)."""
    return {"viewport": dict(SIZE)}


def open_context(playwright, mode: str, folder: str | None = None):
    """A browser context in a mode: kept in folder (a persistent profile, so a login stays), or fresh."""
    if folder:
        return playwright.chromium.launch_persistent_context(folder, **launch_options(mode), **context_options())
    return playwright.chromium.launch(**launch_options(mode)).new_context(**context_options())
