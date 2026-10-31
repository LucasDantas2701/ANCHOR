"""
The desktop program: ANCHOR.exe. It works from the user's data folder, serves the interface on this
computer only, and shows it in its own window (WebView2, the browser component of Windows 10 and 11),
with an icon near the clock. Closing the window keeps ANCHOR running there, for the schedules; Quit,
in the icon's menu, ends it. Opening it again while it runs brings its window back (one ANCHOR at a
time). With --background (how Windows starts it), it opens hidden near the clock.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import requests

from .paths import use_data_dir
from .startup import StartWithWindows

INSTANCE = "instance.json"           # the running ANCHOR's port and code, so a second start can find it


def running_instance(folder: Path):
    """The ANCHOR already running for this user, if any: (port, token)."""
    try:
        info = json.loads((folder / INSTANCE).read_text(encoding="utf-8"))
        answer = requests.post(f"http://127.0.0.1:{info['port']}/api/desktop/show", headers={"X-Anchor-Token": info["token"]},
                               timeout=2)
        if answer.status_code == 200:
            return info["port"], info["token"]
    except Exception:
        pass
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ANCHOR", description="ANCHOR, the desktop program.")
    parser.add_argument("--background", action="store_true", help="start hidden near the clock (how Windows starts it)")
    args = parser.parse_args(argv)
    folder = use_data_dir()
    if running_instance(folder):
        return 0                                             # the running one showed its window

    import uvicorn

    from anchor.ui.__main__ import free_port
    from anchor.ui.server import create_app

    from .setup import Setup

    port, token = free_port(), secrets.token_urlsafe(24)
    shell = Shell(start=StartWithWindows())
    app = create_app("automations", token=token, port=port, run_schedules=True, desktop=shell, setup=Setup())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    (folder / INSTANCE).write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")
    try:
        shell.run(f"http://127.0.0.1:{port}/#token={token}", hidden=args.background)
    finally:
        server.should_exit = True
        try:
            (folder / INSTANCE).unlink()
        except OSError:
            pass
    return 0


class Shell:
    """The window and the icon near the clock (pywebview and pystray; only the installed program uses them)."""

    def __init__(self, start: StartWithWindows):
        self.start = start
        self.window = None
        self.icon = None
        self.quitting = False

    # ------------------------------------------------------------------ what the interface's server calls
    def show(self) -> None:
        if self.window is not None:
            self.window.show()
            self.window.restore()

    # ------------------------------------------------------------------ the window and the icon
    def run(self, url: str, hidden: bool = False) -> None:
        import webview

        self.window = webview.create_window("ANCHOR", url, width=1360, height=880, min_size=(980, 640), hidden=hidden)
        self.window.events.closing += self._closing
        threading.Thread(target=self._tray, daemon=True).start()
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(Path.cwd() / "webview"))

    def _closing(self):
        """Closing the window hides it: ANCHOR keeps running near the clock, for the schedules."""
        if self.quitting:
            return True
        self.window.hide()
        return False

    def _tray(self) -> None:
        import pystray
        from PIL import Image

        icon_file = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "anchor" / "desktop" / "anchor.ico"
        image = Image.open(icon_file) if icon_file.is_file() else Image.new("RGB", (64, 64), "#D2F57A")
        menu = pystray.Menu(
            pystray.MenuItem("Open ANCHOR", lambda: self.show(), default=True),
            pystray.MenuItem("Start with Windows", lambda: self.start.set(not self.start.is_on()),
                             checked=lambda item: self.start.is_on(), visible=self.start.available),
            pystray.MenuItem("Quit", lambda: self.quit()))
        self.icon = pystray.Icon("ANCHOR", image, "ANCHOR", menu)
        self.icon.run()

    def quit(self) -> None:
        self.quitting = True
        if self.icon is not None:
            self.icon.stop()
        if self.window is not None:
            self.window.destroy()


if __name__ == "__main__":
    raise SystemExit(main())
