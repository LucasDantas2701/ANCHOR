"""
The desktop program's routes: the first opening's checks and downloads, starting with Windows, and
bringing the window back when ANCHOR is opened again. Without the desktop program (python -m anchor.ui)
the checks say ready and Start with Windows is not offered.
"""
from __future__ import annotations

from fastapi import Body, HTTPException


def add_routes(app, desktop=None, setup=None) -> None:
    @app.get("/api/setup")
    def status():
        return setup.status() if setup is not None else {"ready": True}

    @app.post("/api/setup/model")
    def model(body: dict = Body(default={})):
        if setup is None:
            raise HTTPException(404, "not in the desktop program")
        profile = str(body.get("profile") or "ollama-small")
        if profile not in setup.downloads:
            raise HTTPException(400, "unknown model")
        return {"started": setup.download_model(profile), **setup.downloads[profile].view()}

    @app.post("/api/setup/browser")
    def browser():
        if setup is None:
            raise HTTPException(404, "not in the desktop program")
        return {"started": setup.download_browser(), **setup.browser.view()}

    @app.get("/api/desktop")
    def info():
        start = getattr(desktop, "start", None)
        available = bool(start is not None and start.available)
        return {"desktop": desktop is not None, "start_with_windows": {"available": available, "on": available and start.is_on()}}

    @app.put("/api/desktop/start")
    def start_with_windows(body: dict = Body(...)):
        start = getattr(desktop, "start", None)
        if start is None or not start.available:
            raise HTTPException(404, "only in the installed program, on Windows")
        return {"on": start.set(bool(body.get("on")))}

    @app.post("/api/desktop/quit")
    def quit_anchor():
        """Ends ANCHOR (the window and the icon near the clock): the same as Quit in the icon's menu."""
        if desktop is None:
            raise HTTPException(404, "not in the desktop program")
        import threading
        threading.Timer(0.3, desktop.quit).start()                 # answer first, then close
        return {"quitting": True}

    @app.post("/api/desktop/show")
    def show():
        if desktop is None:
            raise HTTPException(404, "not in the desktop program")
        desktop.show()
        return {"shown": True}
