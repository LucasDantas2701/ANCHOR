"""
Saved logins in the interface (Settings). The routes take a password only to store it, and never
answer with one: not in a list, not in an error. A password changes or goes; it is never read back.
"""
from __future__ import annotations

from fastapi import Body, HTTPException

from anchor.vault import LoginVault, VaultError


def view(login) -> dict:
    return {"site": login.site, "username": login.username, "created": login.created,
            "last_used": login.last_used, "scheduled": login.scheduled}


def add_routes(app, vault: LoginVault) -> None:
    def text(body: dict, key: str) -> str:
        value = body.get(key, "")
        return value if isinstance(value, str) else ""

    @app.get("/api/logins")
    def logins():
        return [view(x) for x in vault.logins()]

    @app.post("/api/logins")
    def add(body: dict = Body(...)):
        try:
            return view(vault.add(text(body, "site"), text(body, "username"), text(body, "password"), bool(body.get("scheduled"))))
        except VaultError as exc:
            raise HTTPException(400, str(exc))

    @app.put("/api/logins/password")
    def replace(body: dict = Body(...)):
        try:
            vault.replace_password(text(body, "site"), text(body, "username"), text(body, "password"))
        except VaultError as exc:
            raise HTTPException(400, str(exc))
        return {"replaced": True}

    @app.put("/api/logins/scheduled")
    def scheduled(body: dict = Body(...)):
        try:
            vault.set_scheduled(text(body, "site"), text(body, "username"), bool(body.get("scheduled")))
        except VaultError as exc:
            raise HTTPException(400, str(exc))
        return {"scheduled": bool(body.get("scheduled"))}

    @app.delete("/api/logins")
    def delete(site: str, username: str):
        try:
            vault.delete(site, username)
        except VaultError as exc:
            raise HTTPException(404, str(exc))
        return {"deleted": True}
