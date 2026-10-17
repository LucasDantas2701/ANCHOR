"""The local interface's server: who may call it, and what it shows."""
import pytest
from fastapi.testclient import TestClient

from anchor.automations.model import ApprovedPlan, Automation, AutomationStore
from anchor.planner import Goal, Step
from anchor.ui.server import TOKEN_HEADER, create_app

PORT = 8765
HOST = f"127.0.0.1:{PORT}"


@pytest.fixture
def store(tmp_path):
    store = AutomationStore(tmp_path / "automations")
    store.create(Automation(name="new-customer", request="Register {name} and save", url="https://crm.example/new",
                            profile="ollama-small", parameters=["name"]))
    store.save_plan("new-customer", ApprovedPlan(
        steps=[Step(action="fill", description="Name", value="{name}"), Step(action="click", description="Save record")],
        goals=[Goal(id="g1", description="the record is saved")], proven_run="20261017-101500"))
    store.save_run("new-customer", {"mode": "replay", "status": "success", "message": "done", "seconds": 3.24})
    store.create(Automation(name="weekly-report", request="Download the weekly report",
                            url="https://reports.example", profile="ollama-medium"))
    return store


@pytest.fixture
def static(tmp_path):
    folder = tmp_path / "static"
    folder.mkdir()
    (folder / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (folder / "main.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not for the page", encoding="utf-8")
    return folder


@pytest.fixture
def client(store, static):
    app = create_app(store.root, token="the-code", static_dir=static, port=PORT)
    return TestClient(app, base_url=f"http://{HOST}")


def api(client, path, **headers):
    return client.get(path, headers={TOKEN_HEADER: "the-code", **headers})


def test_the_api_needs_the_code_made_at_this_start(client):
    assert client.get("/api/automations").status_code == 401
    assert client.get("/api/automations", headers={TOKEN_HEADER: "a-guess"}).status_code == 401
    assert api(client, "/api/automations").status_code == 200


def test_only_this_computers_address_and_the_apps_own_origin_are_served(client):
    assert api(client, "/api/automations", host="evil.example").status_code == 403
    assert api(client, "/api/automations", origin="https://evil.example").status_code == 403
    assert api(client, "/api/automations", origin=f"http://{HOST}").status_code == 200


def test_the_list_says_what_each_automation_is_and_how_it_last_ran(client):
    rows = {r["name"]: r for r in api(client, "/api/automations").json()}
    assert rows["new-customer"]["learned"] and rows["new-customer"]["steps"] == 2 and rows["new-customer"]["proven"]
    assert rows["new-customer"]["last_run"]["state"] == "checked" and rows["new-customer"]["parameters"] == ["name"]
    assert not rows["weekly-report"]["learned"] and rows["weekly-report"]["last_run"] is None


def test_an_automation_shows_its_plan_and_its_runs(client):
    detail = api(client, "/api/automations/new-customer").json()
    assert [s["description"] for s in detail["plan"]["steps"]] == ["Name", "Save record"]
    assert detail["runs"][0]["seconds"] == 3.2 and detail["recoveries"] == 0
    assert api(client, "/api/automations/none-such").status_code == 404


def test_the_app_is_served_and_nothing_outside_its_folder(client):
    assert client.get("/").text == "<html>app</html>"
    assert client.get("/main.js").text == "console.log(1)"
    assert client.get("/automations/new-customer").text == "<html>app</html>"   # a page of the app
    assert "not for the page" not in client.get("/../secret.txt").text
    assert "not for the page" not in client.get("/%2e%2e/secret.txt").text
