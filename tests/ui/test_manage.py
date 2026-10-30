"""Looking after a saved automation from the interface: fixes and undo, notes, decisions, choices, edit, delete."""
import pytest
from fastapi.testclient import TestClient

from anchor.automations.model import ApprovedPlan, Automation, AutomationStore
from anchor.engine.memory.choices import ChoiceMemory
from anchor.planner import Goal, Step
from anchor.ui.server import create_app

from .test_runs import HEADERS, PORT

PLAN = {"steps": [{"action": "fill", "description": "campo Nome", "value": "{nome}"},
                  {"action": "click", "description": "botão Salvar", "value": None}],
        "goals": [{"id": "g1", "description": "cadastro salvo", "conclusive": True}]}


@pytest.fixture
def store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="cadastro", request="cadastre {nome} e salve", url="https://example.com/form", profile="ollama-small"))
    s.save_plan("cadastro", ApprovedPlan(steps=[Step(**x) for x in PLAN["steps"]], goals=[Goal(**g) for g in PLAN["goals"]]))
    return s


@pytest.fixture
def client(store):
    app = create_app(store.root, token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""}, headless=True)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def test_fixes_are_listed_and_a_plan_fix_is_undone_back_to_the_plan_before_it(client, store):
    store.add_recovery("cadastro", {"method": "replan", "failed_step": PLAN["steps"][1], "reason": "button renamed",
                                    "replaced_by": [{"action": "click", "description": "botão Gravar", "value": None}],
                                    "effect_confirmed": True, "previous_plan": PLAN})
    store.save_plan("cadastro", ApprovedPlan(steps=[Step("fill", "campo Nome", "{nome}"), Step("click", "botão Gravar", None)],
                                             goals=[Goal(**g) for g in PLAN["goals"]]))
    fixes = client.get("/api/automations/cadastro/fixes", headers=HEADERS).json()
    assert fixes[0]["method"] == "replan" and fixes[0]["replaced_by"][0]["description"] == "botão Gravar" and not fixes[0]["undone"]
    assert client.post("/api/automations/cadastro/fixes/1/undo", headers=HEADERS).json()["undone"] is True
    assert store.load_plan("cadastro").steps[1].description == "botão Salvar"
    assert client.post("/api/automations/cadastro/fixes/1/undo", headers=HEADERS).status_code == 400     # already undone


def test_notes_are_added_edited_and_removed(client):
    url = "/api/automations/cadastro/notes"
    assert client.post(url, json={"text": "  "}, headers=HEADERS).status_code == 400
    n = client.post(url, json={"text": "O botão fica no fim da página"}, headers=HEADERS).json()["number"]
    assert client.put(f"{url}/{n}", json={"text": "O botão Salvar fica no fim"}, headers=HEADERS).status_code == 200
    notes = client.get(url, headers=HEADERS).json()
    assert notes[0]["text"] == "O botão Salvar fica no fim" and notes[0]["sent"] is True
    assert client.delete(f"{url}/{n}", headers=HEADERS).json() == {"removed": n}
    assert client.get(url, headers=HEADERS).json() == []


def test_decisions_and_choices_are_listed_and_forgotten(client, store):
    store.add_confirmation("cadastro", {"action": "click", "element": "Excluir", "category": "delete", "decision": "denied"})
    d = client.get("/api/automations/cadastro/decisions", headers=HEADERS).json()
    assert d[0]["decision"] == "denied" and d[0]["category"] == "delete"
    assert client.delete("/api/automations/cadastro/decisions/1", headers=HEADERS).status_code == 200
    assert client.get("/api/automations/cadastro/decisions", headers=HEADERS).json() == []
    ChoiceMemory(store.memory_path("cadastro")).remember("https://example.com/form", "click", "botão Salvar",
                                                         {"role": "button", "tag": "button", "text": "Gravar"})
    c = client.get("/api/automations/cadastro/choices", headers=HEADERS).json()
    assert c[0]["element"] == "Gravar" and c[0]["description"] == "botão Salvar"
    assert client.delete("/api/automations/cadastro/choices", params={"key": c[0]["key"]}, headers=HEADERS).status_code == 200
    assert client.get("/api/automations/cadastro/choices", headers=HEADERS).json() == []


def test_editing_the_request_or_page_forgets_the_plan_and_editing_the_model_does_not(client, store):
    url = "/api/automations/cadastro"
    same = client.put(url, json={"request": "cadastre {nome} e salve", "url": "https://example.com/form", "profile": "ollama-medium"},
                      headers=HEADERS).json()
    assert same["relearn"] is False and store.load_plan("cadastro") is not None and store.load("cadastro").profile == "ollama-medium"
    new = client.put(url, json={"request": "cadastre {nome} com {cpf} e salve", "url": "https://example.com/form",
                                "profile": "ollama-medium"}, headers=HEADERS).json()
    assert new["relearn"] is True and new["parameters"] == ["nome", "cpf"] and store.load_plan("cadastro") is None
    assert client.put(url, json={"request": "", "url": "x", "profile": "y"}, headers=HEADERS).status_code == 400


def test_deleting_needs_the_name_typed_and_removes_everything(client, store):
    (store.folder("cadastro") / "browser").mkdir()
    assert client.delete("/api/automations/cadastro", headers=HEADERS).status_code == 400            # no confirmation
    assert client.delete("/api/automations/cadastro", params={"confirm": "outro"}, headers=HEADERS).status_code == 400
    assert client.delete("/api/automations/cadastro", params={"confirm": "cadastro"}, headers=HEADERS).json() == {"deleted": "cadastro"}
    assert not store.folder("cadastro").exists() and store.names() == []
    from anchor.automations.model import AutomationError
    for bad in ("..", "../x", "a/b", "", "C:\\x"):                       # never a folder outside the automations folder
        with pytest.raises(AutomationError):
            store.delete(bad)


def test_an_automation_in_the_queue_is_not_changed(client, store):
    from anchor.ui.runs import Job
    runs = client.app.state.runs
    runs.jobs[99] = Job(id=99, kind="automation", title="cadastro", spec={"name": "cadastro"}, state="running")
    assert client.put("/api/automations/cadastro", json={"request": "x {a}", "url": "y", "profile": "z"}, headers=HEADERS).status_code == 409
    assert client.delete("/api/automations/cadastro", params={"confirm": "cadastro"}, headers=HEADERS).status_code == 409
    del runs.jobs[99]


def test_the_queue_lists_times_and_results_and_a_waiting_run_leaves_it():
    import threading
    import time

    from anchor.ui.runs import RunManager
    gate = threading.Event()

    def runner(job):
        gate.wait(5)
        return {"state": "checked", "message": "Done."}

    runs = RunManager(runner)
    first, second = runs.submit("automation", "a", {"name": "a"}), runs.submit("request", "r", {})
    time.sleep(0.3)
    items = {i["id"]: i for i in runs.list()}
    assert items[first.id]["position"] == 0 and items[first.id]["started"] and items[second.id]["position"] == 1
    assert items[first.id]["name"] == "a" and items[second.id]["created"] and not items[second.id]["started"]
    runs.stop(second)                                           # waiting: it just leaves the queue
    left = {i["id"]: i for i in runs.list()}[second.id]
    assert left["state"] == "stopped" and left["finished"] and "out of the queue" in left["message"]
    gate.set()
    for _ in range(50):
        if first.state == "checked":
            break
        time.sleep(0.1)
    done = {i["id"]: i for i in runs.list()}[first.id]
    assert done["state"] == "checked" and done["finished"] and done["message"]
