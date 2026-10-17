"""Runs from the interface: the queue, the questions, stopping, and a real run of a saved automation."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from anchor.automations.model import ApprovedPlan, Automation, AutomationStore
from anchor.engine.sensitive import ConfirmationRequest
from anchor.planner import Goal, Step
from anchor.ui.runs import RunManager, WebConfirmer
from anchor.ui.server import TOKEN_HEADER, create_app

PORT = 8766
HEADERS = {TOKEN_HEADER: "the-code"}


def wait_for(check, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("timed out")


def client_for(store, runner=None, headless=True):
    app = create_app(store.root, token="the-code", port=PORT, runner=runner, headless=headless)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


@pytest.fixture
def store(tmp_path):
    store = AutomationStore(tmp_path / "automations")
    store.create(Automation(name="greet", request="Say hello to {name}", url="https://example.com", profile="ollama-small",
                            parameters=["name"]))
    return store


def run_until_done(client, run_id):
    return wait_for(lambda: (r := client.get(f"/api/runs/{run_id}", headers=HEADERS).json())["state"]
                    not in ("queued", "running", "waiting") and r)


def test_runs_go_one_at_a_time_in_the_order_they_came():
    release, order = threading.Event(), []

    def runner(job):
        order.append(job.id)
        release.wait(5)
        return {"state": "checked", "message": "done"}

    manager = RunManager(runner)
    first, second = manager.submit("request", "a", {}), manager.submit("request", "b", {})
    wait_for(lambda: first.state == "running")
    assert second.state == "queued" and manager.position(second) == 1
    release.set()
    wait_for(lambda: second.state == "checked")
    assert order == [first.id, second.id]


def test_a_question_reaches_the_interface_and_its_answer_reaches_the_run(store):
    def runner(job):
        decision = WebConfirmer(job, remembers=True).confirm(
            ConfirmationRequest(action="click", description="Save the record", element="Save", category="submit"))
        return {"state": "checked" if decision else "not_done", "message": f"allowed={bool(decision)} saved={decision.save}"}

    client = client_for(store, runner)
    run = client.post("/api/runs", json={"kind": "automation", "name": "greet", "values": {"name": "Ana"}}, headers=HEADERS).json()
    question = wait_for(lambda: client.get(f"/api/runs/{run['id']}", headers=HEADERS).json()["question"])
    assert question["kind"] == "confirm" and question["element"] == "Save" and question["remembers"]
    assert client.post(f"/api/runs/{run['id']}/answer", json={"number": question["number"], "answer": {"choice": "allow"}},
                       headers=HEADERS).status_code == 200
    done = run_until_done(client, run["id"])
    assert done["state"] == "checked" and done["result"]["message"] == "allowed=True saved=True"
    # an answer to a question that is no longer open is refused
    assert client.post(f"/api/runs/{run['id']}/answer", json={"number": question["number"], "answer": {}},
                       headers=HEADERS).status_code == 409


def test_stopping_with_a_question_open_answers_no_and_keeps_no_decision(store):
    seen = {}

    def runner(job):
        decision = WebConfirmer(job, remembers=True).confirm(
            ConfirmationRequest(action="click", description="Delete", element="Delete", category="delete"))
        seen.update(allowed=bool(decision), saved=decision.save)
        return {"state": "not_done", "message": "refused"}

    client = client_for(store, runner)
    run = client.post("/api/runs", json={"kind": "automation", "name": "greet", "values": {"name": "Ana"}}, headers=HEADERS).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}", headers=HEADERS).json()["question"])
    client.post(f"/api/runs/{run['id']}/stop", headers=HEADERS)
    assert run_until_done(client, run["id"])["state"] == "stopped"
    assert seen == {"allowed": False, "saved": False}


def test_stopping_a_run_takes_effect_at_its_next_step(store):
    def runner(job):
        for i in range(400):
            job.say(f"step {i}")
            time.sleep(0.01)
        return {"state": "checked", "message": "never"}

    client = client_for(store, runner)
    run = client.post("/api/runs", json={"kind": "automation", "name": "greet", "values": {"name": "Ana"}}, headers=HEADERS).json()
    wait_for(lambda: len(client.get(f"/api/runs/{run['id']}", headers=HEADERS).json()["events"]) > 3)
    client.post(f"/api/runs/{run['id']}/stop", headers=HEADERS)
    done = run_until_done(client, run["id"])
    assert done["state"] == "stopped" and done["result"]["message"] == "Stopped by you."
    later = client.get(f"/api/runs/{run['id']}?after=2", headers=HEADERS).json()["events"]
    assert all(e["seq"] > 2 for e in later)


def test_a_run_is_refused_before_it_starts_when_something_is_missing(store):
    client = client_for(store, lambda job: {"state": "checked", "message": ""})
    post = lambda body, **h: client.post("/api/runs", json=body, headers={**HEADERS, **h})
    assert post({"kind": "automation", "name": "greet"}).status_code == 400                   # the value it needs
    assert post({"kind": "automation", "name": "none-such"}).status_code == 404
    assert post({"kind": "request", "request": "Log in with password Abc123!", "url": "example.com",
                 "profile": "ollama-small"}).status_code == 400                                # a password: never
    assert post({"kind": "request", "request": "Search for shoes", "url": "example.com", "profile": "nope"}).status_code == 400
    assert client.post("/api/runs", json={"kind": "automation", "name": "greet", "values": {"name": "x"}}).status_code == 401
    assert post({"kind": "automation", "name": "greet", "values": {"name": "x"}}, origin="https://evil.example").status_code == 403


def test_a_saved_automation_really_runs_and_its_sensitive_step_is_asked_in_the_interface(tmp_path):
    page = tmp_path / "form.html"
    page.write_text("""<!doctype html><html><body><h1>New customer</h1>
      <label for="n">Name</label><input id="n">
      <button onclick="document.getElementById('ok').textContent='Saved: '+document.getElementById('n').value">Save</button>
      <p id="ok"></p></body></html>""", encoding="utf-8")
    store = AutomationStore(tmp_path / "automations")
    store.create(Automation(name="new-customer", request="Register {name} and save", url=page.as_uri(),
                            profile="ollama-small", parameters=["name"]))
    store.save_plan("new-customer", ApprovedPlan(
        steps=[Step(action="fill", description="Name", value="{name}", goal="g1"),
               Step(action="click", description="Save", goal="g1")],
        goals=[Goal(id="g1", description="the customer is saved", conclusive=True)]))
    client = client_for(store, headless=True)
    run = client.post("/api/runs", json={"kind": "automation", "name": "new-customer", "values": {"name": "Ana Souza"}},
                      headers=HEADERS).json()
    question = wait_for(lambda: client.get(f"/api/runs/{run['id']}", headers=HEADERS).json()["question"], 60)
    assert question["kind"] == "confirm" and question["element"] == "Save"
    client.post(f"/api/runs/{run['id']}/answer", json={"number": question["number"], "answer": {"choice": "allow"}}, headers=HEADERS)
    done = wait_for(lambda: (r := client.get(f"/api/runs/{run['id']}", headers=HEADERS).json())["state"]
                    not in ("queued", "running", "waiting") and r, 60)
    assert done["state"] == "checked", done["result"]
    assert store.runs("new-customer")[-1]["status"] == "success"
    assert store.confirmations("new-customer")             # the decision is kept, as in the command line


def test_every_event_has_its_time_of_day():
    from anchor.ui.runs import Job
    job = Job(1, "request", "x", {})
    job.say("Planning...")
    assert len(job.events[0]["at"]) == 8 and job.events[0]["at"].count(":") == 2      # 13:15:02


def test_the_interface_sees_what_the_ai_is_doing_and_why_a_plan_was_not_usable():
    from anchor.planner import Plan, PlanError
    from anchor.ui.execute import StepwisePlanner
    from anchor.ui.runs import Job
    job, seen = Job(1, "request", "x", {}), []

    class Inner:
        language = "pt"

        def __init__(self, progress):
            self.progress, self.last_attempts = progress, []

        def plan(self, *a, **k):
            self.progress("thinking", 40)
            seen.append(dict(job.activity))
            self.progress("writing", 3)                # a second attempt starts from nothing
            seen.append(dict(job.activity))
            self.last_attempts = [("{}", 'step 2: the "fill" action needs a value')]
            raise PlanError("could not generate the plan")

    planner = StepwisePlanner(job, Inner)
    with pytest.raises(PlanError):
        planner.plan("faça login e pesquise")
    assert seen[0]["phase"] == "thinking" and seen[1]["attempt"] == 2 and job.activity is None
    assert job.events[-1]["text"] == 'The AI\'s plan (attempt 1) was not usable: step 2: the "fill" action needs a value'


def test_an_outcome_is_said_in_plain_words_with_what_to_do():
    from anchor.ui.explain import explain
    linkedin = explain({"state": "not_done", "message": 'could not generate the plan: invalid plan after 2 attempts: '
                                                        'step 2: the "fill" action needs a value'})
    assert linkedin["summary"] == "The AI could not make a plan for this page." and "log in" in linkedin["hint"]
    assert explain({"state": "checked", "message": "goal reached"})["summary"] == "Done, and every step was checked."
    assert explain({"state": "not_done", "message": "something new"})["summary"] == "Something new"


def test_with_the_window_hidden_a_login_is_not_waited_for_and_the_person_is_told_why():
    from anchor.ui.runs import Job, WebLoginWaiter
    job = Job(1, "request", "x", {})
    assert WebLoginWaiter(job, can_log_in=False).wait("https://example.com") is False
    assert job.question is None and "browser window is hidden" in job.events[-1]["text"]
