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
