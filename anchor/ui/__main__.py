"""
Starts the local interface: python -m anchor.ui

Serves on this computer only (127.0.0.1), on a free port, and opens the app in the browser with
the code made at this start in the address's fragment (never sent to a server, never logged).
"""
from __future__ import annotations

import argparse
import secrets
import socket
import threading
import webbrowser

import uvicorn

from .server import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m anchor.ui", description="Opens ANCHOR's interface.")
    parser.add_argument("--automations", default="automations", help="the folder of the saved automations")
    parser.add_argument("--port", type=int, default=0, help="the port (default: a free one)")
    parser.add_argument("--no-browser", action="store_true", help="does not open the browser")
    args = parser.parse_args(argv)
    port = args.port or free_port()
    token = secrets.token_urlsafe(24)
    app = create_app(args.automations, token=token, port=port, run_schedules=True)
    address = f"http://127.0.0.1:{port}/#token={token}"
    print(f"ANCHOR is open at {address}")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [address]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
