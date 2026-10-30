"""
Logging in with a saved login, in a run: the only code that reads a password from the vault.

When a run reaches a login page, the agent calls its login waiter. VaultLoginWaiter first tries the
login saved for exactly this site; if there is none, or it does not get in (a wrong password, a code
sent to a phone), it hands over to the person, as before (the fallback waiter). The planner never
knows: the password is typed by this code, only into a password field, only on that exact site, and
the page reader shows a password field's value to the AI only as ********.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from anchor.vault import LoginVault, site_of

# Marks the login form's fields: the visible password field, and the user name field before it (in the
# same form, or the page when there is no form). With no password field, a lone user name field: the
# first step of a two-step login.
_MARK_JS = """() => {
  const seen = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.disabled; };
  document.querySelectorAll('[data-anchor-vault]').forEach((e) => e.removeAttribute('data-anchor-vault'));
  const userLike = (e) => e.tagName === 'INPUT' && ['text', 'email', 'tel', ''].includes((e.getAttribute('type') || '').toLowerCase()) && seen(e);
  const named = (e) => /user|login|email|e-mail|mail|conta|usu|cpf|account|identifier/i.test(
      [e.name, e.id, e.getAttribute('autocomplete'), e.getAttribute('aria-label'), e.placeholder].join(' '));
  const pass = [...document.querySelectorAll('input[type=password]')].find(seen);
  if (pass) {
    pass.setAttribute('data-anchor-vault', 'password');
    const scope = pass.form || document;
    const fields = [...scope.querySelectorAll('input')];
    const before = fields.slice(0, fields.indexOf(pass)).filter(userLike);
    const user = before.reverse().find(named) || before[0];
    if (user) user.setAttribute('data-anchor-vault', 'user');
    return { password: true, user: !!user };
  }
  const users = [...document.querySelectorAll('input')].filter((e) => userLike(e) && named(e));
  if (users.length === 1) { users[0].setAttribute('data-anchor-vault', 'user'); return { password: false, user: true }; }
  return { password: false, user: false };
}"""


class VaultLoginWaiter:
    """A login waiter that first logs in with the login saved for this exact site."""

    def __init__(self, vault: LoginVault, page_of: Callable, fallback=None, report: Callable[[str], None] = print,
                 unattended: bool = False):
        self.vault, self.page_of, self.fallback, self.report = vault, page_of, fallback, report
        self.unattended = unattended            # with no one present, only the logins allowed for scheduled runs

    def wait(self, url: str, signup: bool = False) -> bool:
        if not signup and self.log_in():
            return True
        return self.fallback.wait(url, signup) if self.fallback is not None else False

    # ------------------------------------------------------------------ the saved login
    def _login_for(self, url: str):
        logins = [x for x in self.vault.for_site(url) if x.scheduled or not self.unattended]
        if len(logins) > 1:
            self.report(f"There are {len(logins)} saved logins for {site_of(url)}: log in with the one you want.")
            return None
        return logins[0] if logins else None

    def _form(self, page):
        """The frame with this site's login form (the page itself, or a frame of the same exact site), and what it has."""
        for frame in [page.main_frame] + [f for f in page.frames if f is not page.main_frame]:
            try:
                marks = frame.evaluate(_MARK_JS)
            except Exception:
                continue
            if marks.get("password") or marks.get("user"):
                return frame, marks
        return None, {}

    def log_in(self) -> bool:
        page = self.page_of()
        login = self._login_for(page.url)
        if login is None:
            return False
        frame, marks = self._form(page)
        if frame is None or not _same_site(frame.url, login.site):
            return False                                         # the form is not on the login's exact site
        password = self.vault.password(login)
        if not password:
            self.report(f"The saved login for {login.site} has no password in Windows' Credential Manager: log in yourself.")
            return False
        self.report(f"Logging in to {login.site} as {login.username}, with the saved login.")
        if not marks.get("password"):                            # two steps: the user name first, then the password
            frame.locator("[data-anchor-vault=user]").fill(login.username)
            frame.locator("[data-anchor-vault=user]").press("Enter")
            frame, marks = self._wait_for_password(page, login.site)
            if frame is None:
                self.report("The page did not ask for the password after the user name: log in yourself.")
                return False
        if marks.get("user"):
            field = frame.locator("[data-anchor-vault=user]")
            if (field.input_value() or "").strip() != login.username:
                field.fill(login.username)
        field = frame.locator("[data-anchor-vault=password]")
        if field.evaluate("e => e.type") != "password" or not _same_site(frame.url, login.site):
            return False                                         # checked again right before typing
        field.fill(password)
        field.press("Enter")
        password = None
        if self._got_in(page, login.site):
            self.vault.mark_used(login)
            self.report("Logged in with the saved login.")
            return True
        self.report("The saved login did not get in (a wrong password, or the site asks for a code): log in yourself.")
        return False

    def _wait_for_password(self, page, site: str, seconds: float = 10.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            page.wait_for_timeout(300)
            frame, marks = self._form(page)
            if frame is not None and marks.get("password") and _same_site(frame.url, site):
                return frame, marks
        return None, {}

    def _got_in(self, page, site: str, seconds: float = 15.0) -> bool:
        """In when no password field is left on the page (it went to the site, or asks nothing more)."""
        from anchor.agent.login import password_field
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            page.wait_for_timeout(400)
            try:
                if password_field(page) is None:
                    return True
            except Exception:
                continue                                         # the page is changing
        return False


def _same_site(url: str, site: str) -> bool:
    try:
        return site_of(url) == site
    except Exception:
        return False


def with_vault(fallback, page_of: Callable, report: Callable[[str], None] = print, unattended: bool = False,
               vault: Optional[LoginVault] = None):
    """The run's login waiter: the saved logins first, then the person (the fallback)."""
    return VaultLoginWaiter(vault or LoginVault(), page_of, fallback=fallback, report=report, unattended=unattended)
