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
    parser.add_argument("--self-test", metavar="FILE", help="check that everything the program needs came with it; write the result to FILE")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(Path(args.self_test))
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


def self_test(report: Path) -> int:
    """For the installer's build: checks, from inside the built program, that its parts came with it."""
    checks = {}

    def check(name, test):
        try:
            value = test()
            checks[name] = {"ok": True, "value": str(value)[:200]}
        except Exception as exc:
            checks[name] = {"ok": False, "value": f"{type(exc).__name__}: {exc}"[:300]}

    import importlib

    from anchor import __version__
    check("version", lambda: __version__)
    check("window (pywebview)", lambda: importlib.import_module("webview").__name__)
    check("icon near the clock (pystray)", lambda: importlib.import_module("pystray").__name__)
    check("saved logins (keyring)", lambda: type(importlib.import_module("keyring").get_keyring()).__name__)
    check("spreadsheets (openpyxl)", lambda: importlib.import_module("openpyxl").__version__)

    def driver():
        from playwright._impl._driver import compute_driver_executable
        parts = compute_driver_executable()
        parts = list(parts) if isinstance(parts, (tuple, list)) else [parts]
        missing = [str(p) for p in parts if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(", ".join(missing))
        return parts[0]
    check("browser driver (Playwright)", driver)

    def files():
        from anchor.engine.element_resolver import loader
        from anchor.planner.config import DEFAULT_FILE, load_profiles
        from anchor.ui.server import STATIC
        assert (STATIC / "index.html").is_file(), f"no interface at {STATIC}"
        assert Path(loader.__file__).with_name("index_script.js").is_file(), "no index_script.js"
        assert (Path(__file__).with_name("anchor.ico")).is_file(), "no anchor.ico"
        return sorted(load_profiles(DEFAULT_FILE))
    check("files (interface, profiles, page script, icon)", files)
    check("server", lambda: type(importlib.import_module("anchor.ui.server").create_app).__name__)
    report.write_text(json.dumps(checks, indent=1), encoding="utf-8")
    return 0 if all(c["ok"] for c in checks.values()) else 1


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

        icon_file = Path(__file__).with_name("anchor.ico")
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
