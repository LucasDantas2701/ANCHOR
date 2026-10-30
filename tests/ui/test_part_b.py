"""The interface's part B (first half): the short element of a confirmation, what a failed step tried, the
page changes, what the page showed when a run stopped, and the details file's header."""
from types import SimpleNamespace

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.sensitive import ConfirmationRequest
from anchor.ui.execute import _attach, _detach, about, page_at_end
from anchor.ui.runs import Job, WebConfirmer

LONG = "Salvar cadastro " + "texto ao redor do botão que não ajuda a decidir " * 6


def job() -> Job:
    return Job(id=1, kind="request", title="t", spec={})


class Captures:
    def __init__(self):
        self.asked = []

    def confirm(self, request):
        self.asked.append(request)
        return False


def test_a_confirmation_carries_the_element_in_a_few_words(page):
    page.set_content(f'<form><p>{LONG}</p><input id="n"><button type="submit">Salvar cadastro</button><small>{LONG}</small></form>')
    confirmer = Captures()
    ActionExecutor(page, confirmer=confirmer).click("botão Salvar cadastro")
    assert confirmer.asked[0].shown == "button “Salvar cadastro”"
    page.set_content(f'<form><button type="submit" title="{LONG}">Salvar</button></form>')     # a long name is cut
    ActionExecutor(page, confirmer=confirmer).click("botão Salvar")
    assert confirmer.asked[1].shown.startswith("button “Salvar cadastro") and len(confirmer.asked[1].shown) < 75


def test_the_interface_shows_the_short_element_and_keeps_the_rest_as_context():
    j = job()
    asked = {}
    j.ask = lambda kind, **data: asked.update(kind=kind, **data) or {"choice": "deny"}
    WebConfirmer(j, remembers=False).confirm(ConfirmationRequest("click", "salvar", LONG, "submit", shown="button “Salvar cadastro”"))
    assert asked["shown"] == "button “Salvar cadastro”" and asked["near"].endswith("…") and len(asked["near"]) <= 161
    WebConfirmer(j, remembers=False).confirm(ConfirmationRequest("click", "salvar", LONG, "submit"))
    assert len(asked["shown"]) <= 71                                          # no short form: the start of the long one


def test_a_failed_step_says_what_it_tried_with_the_whole_message_and_a_page_change_is_logged(page, tmp_path):
    (tmp_path / "a.html").write_text("<button>Ir</button>", encoding="utf-8")
    page.goto((tmp_path / "a.html").as_uri())
    j = job()
    executor = ActionExecutor(page)
    live = _attach(j, executor)
    match = SimpleNamespace(id="x", tag="button", role="button", label="", text="Salvar", content="", context="", rect={},
                            score=1.0, page=page, type="", value="", hint="", href="", test_id="", state={}, options=[])
    covered = "Element is covered by <div class=modal>Aceite os cookies</div> " + "x" * 300
    executor.on_result(SimpleNamespace(status="failed", selected_element=match, error=covered))
    (tmp_path / "b.html").write_text("<p>outra</p>", encoding="utf-8")
    page.goto((tmp_path / "b.html").as_uri())
    executor.on_result(SimpleNamespace(status="success", selected_element=None, error=None))
    _detach(j, live)
    tried = next(e for e in j.events if e["type"] == "tried")
    assert "Salvar" in tried["text"] and tried["error"] == covered[:600]
    assert any(e["type"] == "page" and e["text"].endswith("/b.html") for e in j.events)


def test_what_the_page_showed_at_the_end_is_its_address_title_and_visible_messages(page):
    page.set_content('<title>Pedido</title><p role="alert">Cartão recusado</p><p class="error" hidden>escondida</p>'
                     '<div class="toast">Tente de novo</div>')
    seen = page_at_end(page)
    assert seen["title"] == "Pedido" and seen["messages"] == ["Cartão recusado", "Tente de novo"]


def test_the_details_file_header_says_the_version_model_and_browser_mode():
    head = about({"profile": "ollama-small"}, hidden=True)
    assert head["anchor"] and head["browser"].startswith("hidden") and head["profile"] == "ollama-small" and head["model"]
    assert about({"profile": "ollama-small"}, hidden=False)["browser"] == "window"


# --- the second half: how the browser opens, and the run's tabs on the live view ---------------------

from anchor.automations.model import AutomationStore  # noqa: E402
from anchor.browser.launch import SIZE, context_options, launch_options  # noqa: E402
from anchor.ui.execute import Executor, LiveView  # noqa: E402


def test_the_browser_opens_headless_only_for_the_tests_and_otherwise_with_a_real_window():
    assert launch_options("headless") == {"headless": True}
    offscreen, window = launch_options("offscreen"), launch_options("window")
    assert offscreen["headless"] is False and "--window-position=-32000,-32000" in offscreen["args"]
    assert window["headless"] is False and not any(a.startswith("--window-position") for a in window["args"])
    assert all("--disable-notifications" in o["args"] and "--window-size=1366,768" in o["args"] for o in (offscreen, window))
    assert context_options() == {"viewport": SIZE} and "locale" not in context_options()      # the system's language


def test_a_run_uses_a_window_off_screen_unless_the_person_asked_to_see_it(tmp_path):
    store = AutomationStore(tmp_path)
    assert Executor(store, headless=True)._mode(job()) == "headless"
    shown = Job(id=2, kind="request", title="t", spec={"show_browser": True})
    assert Executor(store)._mode(job()) == "offscreen" and Executor(store)._mode(shown) == "window"
    assert Executor(store)._mode(show=True) == "window" and Executor(store)._mode(show=False) == "offscreen"


def test_the_live_view_lists_the_tabs_shows_the_chosen_one_and_goes_back_when_it_closes(page):
    page.set_content("<title>Loja</title><p>a</p>")
    other = page.context.new_page()
    other.set_content("<title>Entrar com o Google</title><p>b</p>")
    j = job()
    live = LiveView(j, lambda: page)
    live.list_tabs()
    assert [t["title"] for t in j.tabs][-2:] == ["Loja", "Entrar com o Google"] and [t["anchor"] for t in j.tabs][-2:] == [True, False]
    assert live.viewed() is page                                            # nobody chose: ANCHOR's tab
    j.viewing = j.tabs[-1]["index"]
    assert live.viewed() is other                                           # the login window, chosen
    other.close()
    assert live.viewed() is page and j.viewing is None                      # closed: back to ANCHOR's


def test_the_person_chooses_a_tab_through_the_interface(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.server import create_app

    from .test_runs import HEADERS, PORT
    app = create_app(tmp_path / "automations", token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""},
                     headless=True)
    client = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    run = client.post("/api/runs", json={"kind": "request", "request": "abra a página", "url": "example.com", "profile": "ollama-small"}, headers=HEADERS).json()
    assert client.post(f"/api/runs/{run['id']}/tab", json={"index": 1}, headers=HEADERS).json() == {"viewing": 1}
    assert client.post(f"/api/runs/{run['id']}/tab", json={"index": None}, headers=HEADERS).json() == {"viewing": None}
    assert client.post(f"/api/runs/{run['id']}/tab", json={"index": 1}).status_code == 401            # the access code
