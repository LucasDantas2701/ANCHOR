"""The desktop program's pieces that run anywhere: the data folder, starting with Windows (a stand-in
registry), and the first opening's checks and downloads (a stand-in Ollama and browser installer)."""
import json
import sys
import time

import pytest

from anchor.desktop import paths
from anchor.desktop.setup import Setup
from anchor.desktop.startup import NAME, StartWithWindows


def test_the_data_folder_is_the_users_and_the_browser_goes_there(tmp_path, monkeypatch):
    import os
    monkeypatch.chdir(os.getcwd())                                             # put the working folder back afterwards
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # use_data_dir points Playwright at the user's browsers: put the variable back as it was afterwards,
    # or the tests after this one would look for Chromium in an empty folder.
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "placeholder")
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH")
    here = paths.use_data_dir()
    assert here == tmp_path / "ANCHOR" and here.is_dir()
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(here / "browsers")


class FakeRegistry:
    """Stands in for winreg: one key, its values."""
    HKEY_CURRENT_USER, REG_SZ = "HKCU", 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path):
        return self._Key()

    CreateKey = OpenKey

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise OSError("no value")
        return self.values[name], 1

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise OSError("no value")
        del self.values[name]


def test_start_with_windows_is_a_value_under_the_users_run_key():
    registry = FakeRegistry()
    start = StartWithWindows(exe=r"C:\Program Files\ANCHOR\ANCHOR.exe", registry=registry)
    assert start.is_on() is False
    assert start.set(True) is True and registry.values[NAME] == r'"C:\Program Files\ANCHOR\ANCHOR.exe" --background'
    assert start.set(False) is False and NAME not in registry.values
    assert start.set(False) is False                                           # already off: still fine


class FakeOllama:
    def __init__(self, running=True, models=(), pull_lines=()):
        self.running, self.models_list, self.pull_lines = running, list(models), pull_lines

    class _Answer:
        def __init__(self, status=200, data=None, lines=()):
            self.status_code, self._data, self._lines = status, data, lines

        def json(self):
            return self._data

        def iter_lines(self):
            return [json.dumps(x).encode() for x in self._lines]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def get(self, url, timeout=None):
        if not self.running:
            raise ConnectionError("refused")
        if url.endswith("/api/tags"):
            return self._Answer(data={"models": [{"name": m} for m in self.models_list]})
        return self._Answer(data={"version": "0.40.4"})

    def post(self, url, json=None, stream=False, timeout=None):
        return self._Answer(lines=self.pull_lines)


def wait(download):
    for _ in range(100):
        if download.state != "running":
            return
        time.sleep(0.05)


def test_the_first_opening_says_what_is_missing(tmp_path):
    browser = tmp_path / "chrome"
    setup = Setup(http=FakeOllama(running=False), browser_path=lambda: str(browser))
    s = setup.status()
    assert s["ollama"] is False and s["model_ready"] is False and s["browser_ready"] is False and s["ready"] is False
    browser.write_text("x")
    medium_only = Setup(http=FakeOllama(models=["qwen3.5:9b"]), browser_path=lambda: str(browser)).status()
    assert medium_only["ready"] is True and [m["ready"] for m in medium_only["models"]] == [False, True]   # one model is enough
    assert Setup(http=FakeOllama(models=[]), browser_path=lambda: str(browser)).status()["ready"] is False


def test_the_model_is_downloaded_through_ollama_with_its_progress(tmp_path):
    lines = [{"status": "pulling manifest"}, {"status": "downloading", "total": 200, "completed": 50}, {"status": "success"}]
    setup = Setup(http=FakeOllama(pull_lines=lines), browser_path=lambda: "")
    assert setup.download_model("ollama-medium") is True
    wait(setup.downloads["ollama-medium"])
    assert setup.downloads["ollama-medium"].state == "done" and setup.downloads["ollama-small"].state == "idle"
    failing = Setup(http=FakeOllama(pull_lines=[{"error": "file does not exist"}]), browser_path=lambda: "")
    failing.download_model("ollama-small")
    wait(failing.downloads["ollama-small"])
    assert failing.downloads["ollama-small"].state == "failed" and "try again" in failing.downloads["ollama-small"].message
    with pytest.raises(ValueError):
        setup.download_model("nope")


def test_the_browser_download_reports_its_percent_and_one_runs_at_a_time():
    setup = Setup(http=FakeOllama(), browser_path=lambda: "")
    script = "import time; [print(f'|  {p}% of 150 MiB', flush=True) or time.sleep(0.05) for p in (10, 55, 100)]"
    assert setup.download_browser(runner=[sys.executable, "-c", script]) is True
    assert setup.download_browser(runner=[sys.executable, "-c", script]) is False              # already running
    wait(setup.browser)
    assert setup.browser.state == "done"
    broken = Setup(http=FakeOllama(), browser_path=lambda: "")
    broken.download_browser(runner=[sys.executable, "-c", "raise SystemExit(1)"])
    wait(broken.browser)
    assert broken.browser.state == "failed"


def test_the_interface_offers_the_checks_and_start_with_windows_only_in_the_desktop_program(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.server import create_app
    from tests.ui.test_runs import HEADERS, PORT

    def client(**kw):
        app = create_app(tmp_path / "a", token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""},
                         headless=True, **kw)
        return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")

    plain = client()                                                    # python -m anchor.ui
    assert plain.get("/api/setup", headers=HEADERS).json() == {"ready": True}
    assert plain.get("/api/desktop", headers=HEADERS).json()["start_with_windows"]["available"] is False
    assert plain.put("/api/desktop/start", json={"on": True}, headers=HEADERS).status_code == 404

    class Shell:
        shown = quits = 0

        def __init__(self):
            self.start = StartWithWindows(exe="ANCHOR.exe", registry=FakeRegistry())
            self.start._forced = True

        def show(self):
            Shell.shown += 1

        def quit(self):
            Shell.quits += 1

    shell = Shell()
    desk = client(desktop=shell, setup=Setup(http=FakeOllama(running=False), browser_path=lambda: ""))
    assert desk.get("/api/setup", headers=HEADERS).json()["ollama"] is False
    assert desk.get("/api/desktop", headers=HEADERS).json()["start_with_windows"] == {"available": True, "on": False}
    assert desk.put("/api/desktop/start", json={"on": True}, headers=HEADERS).json() == {"on": True}
    assert desk.post("/api/desktop/show", headers=HEADERS).status_code == 200 and Shell.shown == 1
    assert desk.post("/api/desktop/show").status_code == 401                                   # the access code
    assert desk.post("/api/desktop/quit", headers=HEADERS).json() == {"quitting": True}
    time.sleep(0.5)
    assert Shell.quits == 1 and plain.post("/api/desktop/quit", headers=HEADERS).status_code == 404
    assert [p.get("downloaded") for p in desk.get("/api/profiles", headers=HEADERS).json()] == [False, False]
    assert "downloaded" not in plain.get("/api/profiles", headers=HEADERS).json()[0]


def test_a_windowed_program_without_stdout_logs_to_a_file_and_the_server_can_start(tmp_path):
    """ANCHOR.exe has no stdout or stderr: the server's logging must not stop it as it opens."""
    import subprocess
    code = (
        "import sys; sys.stdout = None; sys.stderr = None\n"
        "from pathlib import Path\n"
        "from anchor.desktop.app import log_to_file\n"
        f"log_to_file(Path({str(tmp_path)!r}))\n"
        "import uvicorn\n"
        "uvicorn.Config(lambda s, r, x: None, host='127.0.0.1', port=1, log_level='warning')\n"
        "print('server configured')\n")
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert "server configured" in (tmp_path / "anchor.log").read_text(encoding="utf-8")


def test_the_browser_download_starts_with_no_console_window_on_windows(monkeypatch):
    import subprocess

    from anchor.desktop import setup as setup_module
    if not hasattr(subprocess, "STARTUPINFO"):                       # these exist only on Windows: stand in for them
        class Info:
            dwFlags, wShowWindow = 0, None
        monkeypatch.setattr(subprocess, "STARTUPINFO", Info, raising=False)
        for name, value in (("STARTF_USESHOWWINDOW", 1), ("SW_HIDE", 0), ("CREATE_NO_WINDOW", 0x08000000)):
            monkeypatch.setattr(subprocess, name, value, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    hidden = setup_module.no_window()
    assert hidden["creationflags"] == subprocess.CREATE_NO_WINDOW and hidden["startupinfo"].wShowWindow == subprocess.SW_HIDE
    monkeypatch.setattr(sys, "platform", "linux")
    assert setup_module.no_window() == {}
