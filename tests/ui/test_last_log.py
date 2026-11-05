"""An automation keeps its last runs' details, so the last run's log can be downloaded later."""
import json
import time

from anchor.automations.model import Automation, AutomationStore


def test_the_store_keeps_the_last_ten_logs(tmp_path):
    store = AutomationStore(tmp_path / "a")
    store.create(Automation(name="r", request="x", url="https://example.com", profile="ollama-small"))
    assert store.last_log("r") is None
    for run in range(12):                                    # many in the same second: none overwrites another
        store.save_log("r", run, {"run": run})
    logs = sorted((store.folder("r") / "logs").glob("*.json"))
    assert len(logs) == AutomationStore.LOGS_KEPT and logs[0].name.endswith("-run2.json")
    assert json.loads(store.last_log("r").read_text(encoding="utf-8"))["run"] == 11


def test_a_finished_automation_run_keeps_its_log_and_the_page_offers_it(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.server import create_app

    from .test_runs import HEADERS, PORT
    store = AutomationStore(tmp_path / "a")
    store.create(Automation(name="report", request="baixe o relatório", url="https://example.com", profile="ollama-small"))
    app = create_app(store.root, token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": "done"}, headless=True)
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    assert c.get("/api/automations/report", headers=HEADERS).json()["has_log"] is False
    assert c.get("/api/automations/report/last-log", headers=HEADERS).status_code == 404
    job = app.state.runs.submit("automation", "report", {"name": "report", "values": {}})
    for _ in range(100):
        if job.state not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert c.get("/api/automations/report", headers=HEADERS).json()["has_log"] is True
    log = c.get("/api/automations/report/last-log", headers=HEADERS)
    assert log.status_code == 200 and log.json()["run"] == job.id and log.json()["result"]["message"] == "done"
    app.state.runs.submit("request", "a one-off request", {"request": "x"})                      # not an automation: no log
    assert c.get("/api/automations/nope/last-log", headers=HEADERS).status_code == 404


def test_the_title_bar_colors_and_the_theme_route(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.desktop.app import colorref
    from anchor.ui.server import create_app

    from .test_runs import HEADERS, PORT
    assert colorref(0x0C0A12) == 0x120A0C and colorref(0xF3F1F7) == 0xF7F1F3

    class Shell:
        theme = "dark"
        start = None

        def set_theme(self, theme):
            self.theme = theme

    shell = Shell()
    app = create_app(tmp_path / "a", token="the-code", port=PORT, runner=lambda job: {}, headless=True, desktop=shell)
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    assert c.put("/api/desktop/theme", json={"theme": "light"}, headers=HEADERS).json() == {"theme": "light"}
    plain = TestClient(create_app(tmp_path / "b", token="the-code", port=PORT, runner=lambda job: {}, headless=True),
                       base_url=f"http://127.0.0.1:{PORT}")
    assert plain.put("/api/desktop/theme", json={"theme": "light"}, headers=HEADERS).status_code == 404
