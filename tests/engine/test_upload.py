"""Uploads: the file goes into the field or through the chooser, the path must exist and come from the request."""

from pathlib import Path

import pytest

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.sensitive import ConfirmationRequest, classify
from anchor.planner import Plan, PlanError, Step
from anchor.planner.plan import check_values_from_request

ROOT = Path(__file__).resolve().parents[2]
FIXTURES, FILES = ROOT / "eval" / "fixtures", ROOT / "eval" / "fixtures" / "files"
names = "() => ['proof', 'cv', 'photo'].map(id => (document.getElementById(id).files[0] || {}).name || null)"


def open_form(page, name="application.html"):
    page.goto((FIXTURES / name).as_uri())


def test_a_file_field_and_a_button_that_opens_the_chooser_both_work(page):
    open_form(page)
    executor = ActionExecutor(page)
    assert executor.upload("Comprovante de residência", str(FILES / "comprovante.pdf")).status == "success"
    assert executor.upload("Anexar currículo", str(FILES / "curriculo.pdf")).status == "success"
    assert page.evaluate(names) == ["comprovante.pdf", "curriculo.pdf", None]


def test_a_missing_file_is_refused_before_touching_the_page(page):
    open_form(page)
    result = ActionExecutor(page).upload("Anexar currículo", str(FILES / "nao-existe.pdf"))
    assert result.status == "no_such_file" and page.evaluate(names) == [None, None, None]


def test_an_element_that_opens_no_chooser_fails(page):
    open_form(page)
    result = ActionExecutor(page).upload("Enviar candidatura", str(FILES / "curriculo.pdf"), timeout_ms=1500)
    assert result.status == "no_file_input"


def test_every_upload_is_sensitive_and_a_denial_sends_nothing(page):
    assert classify("upload", "Foto de perfil") == "upload"

    class Denies:
        def confirm(self, request: ConfirmationRequest) -> bool:
            return False

    open_form(page)
    result = ActionExecutor(page, confirmer=Denies()).upload("Anexar currículo", str(FILES / "curriculo.pdf"))
    assert result.status == "denied" and page.evaluate(names) == [None, None, None]


def test_the_path_must_come_from_the_request():
    steps = [Step("upload", "Anexar currículo", "C:/Users/ana/Documentos/cv.pdf")]
    with pytest.raises(PlanError):
        check_values_from_request(steps, ["anexe o meu currículo"])          # the model picked a file
    check_values_from_request(steps, ["anexe o currículo C:/Users/ana/Documentos/cv.pdf"])


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls = list(steps), 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_the_agent_stops_on_a_missing_file_without_replanning(page):
    open_form(page)
    planner = OnePlan(("upload", "Anexar currículo", str(FILES / "nao-existe.pdf")))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("anexe o currículo")
    assert result.status == "failed" and "does not exist" in result.message and planner.calls == 1


def test_only_requests_about_sending_a_file_hear_about_uploads():
    from anchor.planner.prompt import SYSTEM, system_prompt
    from anchor.planner.reading import wants_upload
    assert wants_upload("anexe o currículo C:/cv.pdf") and wants_upload("attach my resume")
    assert not wants_upload("Pesquise Pi Network") and not wants_upload("Preencha o usuário lucas.dantas")
    assert system_prompt("pt") == SYSTEM and "upload" in system_prompt("pt", uploads=True)


def test_the_verb_in_the_message_is_the_one_the_user_wrote():
    from anchor.planner.plan import check_request
    with pytest.raises(PlanError) as error:
        check_request([Step("fill", "Search", "x")], [], "download the September invoice", "en")
    assert '"baixar"' in str(error.value)                                # the model: unchanged
    assert '"download"' in error.value.user_text() and "baixar" not in error.value.user_text()



def test_sending_a_file_is_done_by_the_upload_but_sending_the_form_still_needs_the_click():
    from anchor.planner.plan import check_request
    upload = [Step("upload", "Comprovante de residência", "eval/fixtures/files/comprovante.pdf")]
    check_request(upload, [], "envie o comprovante eval/fixtures/files/comprovante.pdf")   # a file: done
    with pytest.raises(PlanError):
        check_request(upload, [], "anexe o comprovante eval/fixtures/files/comprovante.pdf e envie a candidatura")


def test_a_click_on_an_attach_button_with_a_path_in_the_request_is_an_upload(page):
    open_form(page, "application_en.html")
    request = "attach the resume eval/fixtures/files/resume.pdf"
    result = Agent(page, OnePlan(("click", "Attach resume", None)), ActionExecutor(page), report=None).run(request)
    assert result.ok, result.message
    assert page.evaluate(names) == [None, "resume.pdf", None] and result.records[0].step.action == "upload"


def test_with_two_paths_each_field_gets_the_file_that_matches_it(page):
    open_form(page)
    request = "anexe o currículo eval/fixtures/files/curriculo.pdf e a foto eval/fixtures/files/foto.png"
    planner = OnePlan(("click", "Foto de perfil", None), ("click", "Anexar currículo", None))
    result = Agent(page, planner, ActionExecutor(page), report=None).run(request)
    assert result.ok, result.message
    assert page.evaluate(names) == [None, "curriculo.pdf", "foto.png"]


def test_a_file_sent_through_another_field_is_blocked(page):
    open_form(page)
    request = "envie o comprovante de residência eval/fixtures/files/comprovante.pdf"
    planner = OnePlan(("upload", "Anexar currículo", "eval/fixtures/files/comprovante.pdf"))
    result = Agent(page, planner, ActionExecutor(page), report=None).run(request)
    assert not result.ok and result.records[0].status == "blocked" and page.evaluate(names) == [None, None, None]


def test_a_file_no_other_field_matches_is_not_blocked(page, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4\n")
    open_form(page)
    planner = OnePlan(("upload", "Anexar currículo", str(cv)))
    result = Agent(page, planner, ActionExecutor(page), report=None).run(f"anexe meu cv {cv}")
    assert result.ok, result.message and page.evaluate(names)[1] == "cv.pdf"
