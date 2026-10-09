"""
Logging in by hand: ANCHOR never types a password.

Credentials never go through the model. When a task needs a login, the agent stops, the user
logs in in the browser window, and the agent goes on. With a persistent browser profile
(--browser-profile, or a saved automation's own profile), the session is kept for the next runs.

    request_has_password(request): a request that carries a password ("senha: 1234") is refused
        before anything reaches the model.
    wants_login(request): the request asks to log in ("faça login", "sign in").
    password_field(page): the name of a visible password field on the page, if any.
    TerminalLoginWaiter: asks the user, in the terminal, to log in and press Enter.
"""

from __future__ import annotations

import re
import sys
from typing import Callable, Optional

from playwright.sync_api import Page

from anchor.i18n import t

# "senha: 1234", "password hunter2", "senha é abc123", 'password "x"': a secret after the word.
_SECRET = re.compile(
    r"\b(senha|password|passwd|pwd|passcode)\b\s*(?:[:=]|é|e|is)?\s*(\"[^\"]+\"|'[^']+'|\S+)", re.IGNORECASE)
_LOGIN = re.compile(
    r"\b(fa[çc]a\s+(o\s+)?login|logue|logar|fazer\s+login|entre\s+(na|com\s+a)\s+(minha\s+)?conta|"
    r"entrar\s+na\s+conta|acesse\s+(a|minha)\s+conta|log\s*in|sign\s*in|login)\b", re.IGNORECASE)


def request_has_password(request: str) -> bool:
    """True when the request seems to carry a password: a word for it followed by a secret-looking value."""
    for match in _SECRET.finditer(request or ""):
        raw = match.group(2)
        value = raw.strip("\"'.,;")
        if raw[:1] in ("\"", "'") or any(c.isdigit() for c in value) or re.search(r"[^\w\s]", value):
            return True
        if len(value) >= 6 and match.group(0).count(":") + match.group(0).count("=") > 0:
            return True                     # "senha: hunter" (a value after a colon)
    return False


def wants_login(request: str) -> bool:
    return bool(_LOGIN.search(request or ""))


_PASSWORD_JS = """
() => {
  for (const e of document.querySelectorAll('input[type=password]')) {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.disabled)
      return {name: ((e.labels && e.labels[0] && e.labels[0].innerText) || e.getAttribute('aria-label')
                    || e.placeholder || e.name || 'password').trim(), filled: e.value.length > 0};
  }
  return null;
}
"""


def password_field(page: Page) -> Optional[dict]:
    """{"name", "filled"} for the first visible password field on the page, or None."""
    try:
        return page.evaluate(_PASSWORD_JS)
    except Exception:
        return None


class TerminalLoginWaiter:
    """Asks the user to log in in the browser and press Enter. With no one at the terminal, it cannot."""

    def __init__(self, input_fn: Callable[[str], str] = input, output: Callable[[str], None] = print,
                 interactive: Optional[bool] = None):
        self.input_fn, self.output = input_fn, output
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def wait(self, url: str, signup: bool = False) -> bool:
        """True when the user says the login is done; False when they give up (or no one is there)."""
        if not self.interactive:
            return False
        self.output("\n" + t("login.needed_signup" if signup else "login.needed", url=url))
        try:
            answer = self.input_fn(t("login.prompt") + " ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer not in ("q", "quit", "sair", "cancel", "cancelar")
