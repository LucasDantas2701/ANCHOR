"""
Saved logins. The password goes to the system's credential store (Windows' Credential Manager,
through the keyring library); a local file keeps only what is not secret (the site, the user name,
dates, and whether scheduled runs may use it). No interface, API or log ever returns a password:
only the code that fills a password field on that exact site reads it (anchor/vault/fill.py).

A login belongs to an exact site: scheme, host and port ("https://accounts.example.com"). It is not
used on another subdomain ("https://mail.example.com"), and only https sites (or this computer) are
accepted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

SERVICE = "ANCHOR login {site}"           # the credential's name in the store, one per site and user name
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


class VaultError(ValueError):
    pass


def site_of(url: str) -> str:
    """The exact site a login belongs to: scheme://host[:port], lower case. Refuses what is not a web
    address, and plain http except on this computer."""
    text = (url or "").strip()
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        scheme, host, port = parts.scheme.lower(), (parts.hostname or "").lower(), parts.port
    except ValueError:                          # a malformed address (a bad port, for one)
        raise VaultError("write the site's address, like https://accounts.example.com")
    if scheme not in ("http", "https") or not host:
        raise VaultError("write the site's address, like https://accounts.example.com")
    if scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
        raise VaultError("only https sites (or this computer): a login over plain http could be read on the way")
    return f"{scheme}://{host}{f':{port}' if port else ''}"


@dataclass
class Login:
    site: str
    username: str
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_used: str = ""
    scheduled: bool = False              # may a run with no one present use it? (off until the person turns it on)


class LoginVault:
    def __init__(self, path: str | Path = "memory/logins.json", keyring=None):
        self.path = Path(path)
        if keyring is None:
            import keyring as keyring_module
            keyring = keyring_module
        self.keyring = keyring

    # ------------------------------------------------------------------ the local list (nothing secret)
    def logins(self) -> list[Login]:
        if not self.path.exists():
            return []
        return [Login(**x) for x in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self, logins: list[Login]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(x) for x in logins], ensure_ascii=False, indent=1), encoding="utf-8")

    def _find(self, logins: list[Login], site: str, username: str) -> Optional[Login]:
        return next((x for x in logins if x.site == site and x.username == username), None)

    def for_site(self, url: str) -> list[Login]:
        """The logins saved for exactly this page's site (none for another subdomain, scheme or port)."""
        try:
            site = site_of(url)
        except VaultError:
            return []
        return [x for x in self.logins() if x.site == site]

    # ------------------------------------------------------------------ changes
    def add(self, url: str, username: str, password: str, scheduled: bool = False) -> Login:
        site, username = site_of(url), username.strip()
        if not username:
            raise VaultError("write the user name (or e-mail) you log in with")
        if not password:
            raise VaultError("write the password")
        logins = self.logins()
        if self._find(logins, site, username):
            raise VaultError("this login is already saved; replace its password instead")
        self.keyring.set_password(SERVICE.format(site=site), username, password)
        login = Login(site, username, scheduled=bool(scheduled))
        self._save(logins + [login])
        return login

    def replace_password(self, site: str, username: str, password: str) -> None:
        if not password:
            raise VaultError("write the new password")
        if not self._find(self.logins(), site, username):
            raise VaultError("no such login")
        self.keyring.set_password(SERVICE.format(site=site), username, password)

    def set_scheduled(self, site: str, username: str, scheduled: bool) -> None:
        logins = self.logins()
        login = self._find(logins, site, username)
        if not login:
            raise VaultError("no such login")
        login.scheduled = bool(scheduled)
        self._save(logins)

    def delete(self, site: str, username: str) -> None:
        logins = self.logins()
        login = self._find(logins, site, username)
        if not login:
            raise VaultError("no such login")
        try:
            self.keyring.delete_password(SERVICE.format(site=site), username)
        except Exception:                       # already gone from the store: the list entry still goes
            pass
        self._save([x for x in logins if x is not login])

    # ------------------------------------------------------------------ for the filler only
    def password(self, login: Login) -> Optional[str]:
        """The password, for the code that fills a password field on its exact site; nothing else calls this."""
        return self.keyring.get_password(SERVICE.format(site=login.site), login.username)

    def mark_used(self, login: Login) -> None:
        logins = self.logins()
        found = self._find(logins, login.site, login.username)
        if found:
            found.last_used = datetime.now().isoformat(timespec="seconds")
            self._save(logins)
