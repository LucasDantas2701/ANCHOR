"""
The first opening's checks, and the downloads they offer: is Ollama installed and running, is the
small model there, and is the browser ANCHOR drives downloaded. Each download runs in the background
and reports its progress, for the interface's setup screen.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import requests

OLLAMA = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD = "https://ollama.com/download"


class Download:
    """One download's progress: state (idle, running, done, failed), percent and a sentence."""
    def __init__(self):
        self.state, self.percent, self.message = "idle", 0.0, ""
        self.lock = threading.Lock()

    def view(self) -> dict:
        return {"state": self.state, "percent": round(self.percent, 1), "message": self.message}

    def run(self, work: Callable[["Download"], None]) -> bool:
        with self.lock:
            if self.state == "running":
                return False
            self.state, self.percent, self.message = "running", 0.0, "Starting…"

        def go():
            try:
                work(self)
                self.state, self.percent = "done", 100.0
            except Exception as exc:
                self.state, self.message = "failed", f"It did not finish: {exc}. Check the internet connection and try again."
        threading.Thread(target=go, daemon=True).start()
        return True


class Setup:
    def __init__(self, model: str = "qwen3.5:4b", ollama: str = OLLAMA, browser_path: Optional[Callable[[], str]] = None,
                 http=requests):
        self.model, self.ollama, self.http = model, ollama, http
        self.browser_path = browser_path or _chromium_path
        self.browser, self.model_download = Download(), Download()

    # ------------------------------------------------------------------ what is there
    def ollama_running(self) -> bool:
        try:
            return self.http.get(self.ollama + "/api/version", timeout=2).status_code == 200
        except Exception:
            return False

    def models(self) -> list[str]:
        try:
            return [m["name"] for m in self.http.get(self.ollama + "/api/tags", timeout=3).json().get("models", [])]
        except Exception:
            return []

    def browser_ready(self) -> bool:
        try:
            return Path(self.browser_path()).is_file()
        except Exception:
            return False

    def status(self) -> dict:
        running = self.ollama_running()
        have = self.models() if running else []
        model_ok = any(m == self.model or m.split(":")[0] == self.model.split(":")[0] and m.startswith(self.model) for m in have)
        browser_ok = self.browser_ready()
        return {"ollama": running, "ollama_download": OLLAMA_DOWNLOAD, "model": self.model, "model_ready": model_ok,
                "browser_ready": browser_ok, "ready": running and model_ok and browser_ok,
                "browser_download": self.browser.view(), "model_download": self.model_download.view()}

    # ------------------------------------------------------------------ downloads
    def download_model(self) -> bool:
        def work(d: Download):
            with self.http.post(self.ollama + "/api/pull", json={"model": self.model, "stream": True}, stream=True, timeout=None) as answer:
                for line in answer.iter_lines():
                    if not line:
                        continue
                    part = json.loads(line)
                    if part.get("error"):
                        raise RuntimeError(part["error"])
                    if part.get("total"):
                        d.percent = 100.0 * part.get("completed", 0) / part["total"]
                    d.message = part.get("status", "")
        return self.model_download.run(work)

    def download_browser(self, runner=None) -> bool:
        """Playwright's own installer, which downloads Chromium into the data folder (PLAYWRIGHT_BROWSERS_PATH)."""
        def work(d: Download):
            command, env = (runner, None) if runner else _playwright_install_command()
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
            for line in process.stdout:
                found = re.search(r"(\d+(?:\.\d+)?)%", line)
                if found:
                    d.percent = float(found.group(1))
                d.message = "Downloading the browser…"
            if process.wait() != 0:
                raise RuntimeError("the browser download stopped")
        return self.browser.run(work)


def _chromium_path() -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return p.chromium.executable_path


def _playwright_install_command() -> tuple[list[str], dict]:
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    driver = compute_driver_executable()
    parts = list(driver) if isinstance(driver, (tuple, list)) else [str(driver)]
    return parts + ["install", "chromium"], get_driver_env()
