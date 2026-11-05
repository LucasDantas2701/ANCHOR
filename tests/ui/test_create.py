"""Creating automations from the interface: from scratch, from a checked request, and seeing a plan first."""
import pytest
from fastapi.testclient import TestClient

from anchor.automations.model import AutomationStore
from anchor.planner import Goal, Plan, Step
from anchor.ui.server import TOKEN_HEADER, create_app

from .test_runs import HEADERS, PORT, run_until_done, wait_for


def client_for(store, runner=None):
    return TestClient(create_app(store.root, token="the-code", port=PORT, runner=runner, headless=True),
                      base_url=f"http://127.0.0.1:{PORT}")


@pytest.fixture
def store(tmp_path):
    return AutomationStore(tmp_path / "automations")


def test_an_automation_is_created_with_the_values_its_request_names(store):
    client = client_for(store, lambda job: {"state": "checked", "message": ""})
    new = client.post("/api/automations", json={"name": "register-customer", "request": "Register {name}, phone {phone}, and save",
                                                 "url": "crm.example.com", "profile": "ollama-small"}, headers=HEADERS)
    assert new.status_code == 200 and new.json()["parameters"] == ["name", "phone"]
    assert store.load("register-customer").url == "https://crm.example.com" and not new.json()["learned"]
    post = lambda **body: client.post("/api/automations", json={"name": "x", "request": "Search", "url": "a.com",
                                                                "profile": "ollama-small", **body}, headers=HEADERS)
    assert post(name="register-customer").status_code == 400                          # the name is taken
    assert post(request="Log in with password Abc123!").status_code == 400             # never a password
    assert post(profile="nope").status_code == 400
    assert post(request="").status_code == 400


def test_a_checked_request_becomes_an_automation_with_the_plan_of_that_run(store):
    def runner(job):
        job.learned = {"steps": [{"action": "fill", "description": "Name", "value": "Ana", "goal": "g1", "expect": None},
                                 {"action": "click", "description": "Save", "value": None, "goal": "g1", "expect": None}],
                       "goals": [{"id": "g1", "description": "saved", "conclusive": True}], "language": "en"}
        return {"state": "checked", "message": "goal reached"}

    client = client_for(store, runner)
    run = client.post("/api/runs", json={"kind": "request", "request": "Register Ana and save", "url": "crm.example.com",
                                         "profile": "ollama-small"}, headers=HEADERS).json()
    assert run_until_done(client, run["id"])["can_save"]
    saved = client.post(f"/api/runs/{run['id']}/save", json={"name": "register-ana"}, headers=HEADERS)
    assert saved.status_code == 200 and saved.json()["learned"] and saved.json()["steps"] == 2
    plan = store.load_plan("register-ana")
    assert [s.description for s in plan.steps] == ["Name", "Save"] and plan.proven_run == ""      # one clean run first
    assert client.post(f"/api/runs/{run['id']}/save", json={"name": "register-ana"}, headers=HEADERS).status_code == 400


def test_only_a_checked_request_can_be_saved(store):
    client = client_for(store, lambda job: {"state": "not_done", "message": "not found"})
    run = client.post("/api/runs", json={"kind": "request", "request": "Do it", "url": "a.com", "profile": "ollama-small"},
                      headers=HEADERS).json()
    assert not run_until_done(client, run["id"])["can_save"]
    assert client.post(f"/api/runs/{run['id']}/save", json={"name": "x"}, headers=HEADERS).status_code == 409


def test_a_real_request_keeps_the_steps_that_worked_to_save_them(tmp_path, monkeypatch):
    import anchor.ui.execute as execute
    page = tmp_path / "crm.html"
    page.write_text('<label for="n">Name</label><input id="n"><button onclick="this.textContent=\'Shown\'">Show</button>',
                    encoding="utf-8")

    class FakePlanner:
        language, last_attempts, last_refusals = "en", [], []

        def __init__(self):
            self.calls = 0

        def language_for(self, request):
            return "en"

        def plan(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return Plan(steps=[Step("fill", "Name", "Ana", goal="g1"), Step("click", "Show", goal="g1")],
                            goals=[Goal("g1", "the name is shown")])
            return Plan(steps=[])

    class Profile:
        def planner(self, **kwargs):
            return FakePlanner()

    monkeypatch.setattr(execute, "get_profile", lambda name: Profile())
    store = AutomationStore(tmp_path / "automations")
    client = client_for(store)
    run = client.post("/api/runs", json={"kind": "request", "request": "Type Ana in the name and show it", "url": str(page),
                                         "profile": "ollama-small"}, headers=HEADERS).json()
    done = wait_for(lambda: (r := client.get(f"/api/runs/{run['id']}", headers=HEADERS).json())["state"]
                    not in ("queued", "running", "waiting") and r, 60)
    assert done["state"] == "checked" and done["can_save"], done["result"]
    assert client.post(f"/api/runs/{run['id']}/save", json={"name": "show-ana"}, headers=HEADERS).status_code == 200
    assert [s.action for s in store.load_plan("show-ana").steps] == ["fill", "click"]


def test_seeing_the_plan_first_does_not_run_it(store):
    seen = {}

    def runner(job):
        seen["kind"] = job.kind
        return {"state": "planned", "message": "The AI would do 1 steps.",
                "plan": {"steps": [{"action": "click", "description": "Search", "value": None, "goal": None}], "goals": []}}

    client = client_for(store, runner)
    run = client.post("/api/runs", json={"kind": "plan", "request": "Search for shoes", "url": "shop.example.com",
                                         "profile": "ollama-small"}, headers=HEADERS).json()
    done = run_until_done(client, run["id"])
    assert seen["kind"] == "plan" and done["result"]["plan"]["steps"][0]["description"] == "Search" and not done["can_save"]
    assert done["state"] == "planned" and "Nothing was done" in done["result"]["summary"]      # never "checked": nothing was
