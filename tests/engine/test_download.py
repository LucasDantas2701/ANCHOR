"""Downloads: the file is saved, never overwritten, a click with no file fails, and it is sensitive."""

from pathlib import Path

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.sensitive import ConfirmationRequest, classify
from anchor.planner import Plan, Step

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def open_documents(page, name="documents.html"):
    page.goto((FIXTURES / name).as_uri())


def test_a_download_is_saved_with_the_suggested_name_and_never_overwrites(page, tmp_path):
    open_documents(page)
    executor = ActionExecutor(page)
    executor.download_dir = tmp_path
    first = executor.download("Baixar relatório de vendas")
    second = executor.download("Baixar relatório de vendas")
    assert first.status == "success" and first.value["name"] == "relatorio-vendas.csv"
    assert second.value["name"] == "relatorio-vendas (2).csv"
    assert "Norte;61800" in Path(first.value["path"]).read_text(encoding="utf-8")
    assert first.value["bytes"] == Path(first.value["path"]).stat().st_size


def test_a_click_that_downloads_nothing_fails(page, tmp_path):
    open_documents(page)
    executor = ActionExecutor(page)
    executor.download_dir = tmp_path
    result = executor.download("Ver política de privacidade", timeout_ms=1500)
    assert result.status == "no_download" and not list(tmp_path.iterdir())


def test_every_download_is_sensitive_whatever_the_label():
    assert classify("download", "Get the app") == "download"
    assert classify("download", "Relatório") == "download"
    assert classify("click", "Relatório") is None


class Denies:
    def __init__(self):
        self.asked = []

    def confirm(self, request: ConfirmationRequest) -> bool:
        self.asked.append(request)
        return False


def test_a_denied_download_saves_nothing(page, tmp_path):
    open_documents(page)
    confirmer = Denies()
    executor = ActionExecutor(page, confirmer=confirmer)
    executor.download_dir = tmp_path
    result = executor.download("Baixar contrato")
    assert result.status == "denied" and confirmer.asked[0].category == "download" and not list(tmp_path.iterdir())


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls, self.histories = list(steps), 0, []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.calls += 1
        self.histories.append(list(history or []))
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_the_agent_keeps_the_downloaded_file(page, tmp_path):
    open_documents(page, "documents_en.html")
    result = Agent(page, OnePlan(("download", "Download contract", None)), ActionExecutor(page),
                   report=None, output_dir=tmp_path).run("download the service contract")
    assert result.ok, result.message
    (file,) = result.extractions
    assert file["kind"] == "file" and file["name"] == "service-contract.pdf" and Path(file["path"]).parent == tmp_path


def test_a_click_with_no_file_is_a_reason_for_the_planner(page, tmp_path):
    open_documents(page)
    planner = OnePlan(("download", "Ver política de privacidade", None))
    result = Agent(page, planner, ActionExecutor(page), report=None, output_dir=tmp_path).run("baixe a política")
    assert not result.ok and result.records[0].status == "no_download"
    assert any("não baixou" in " ".join(h) for h in planner.histories)


def test_only_requests_about_files_hear_about_downloads():
    from anchor.planner.prompt import SYSTEM, system_prompt
    from anchor.planner.reading import wants_file
    assert wants_file("baixe o relatório de vendas") and wants_file("download the September invoice")
    assert not wants_file("Selecione a Ana e a Carla na lista") and not wants_file("Pesquise Pi Network")
    assert system_prompt("pt") == SYSTEM and "download" in system_prompt("pt", files=True)


def test_file_checks_read_the_downloaded_file(tmp_path):
    from eval.plan_run import extraction_checks
    saved = tmp_path / "relatorio-vendas.csv"
    saved.write_text("Região;Receita\nNorte;61800\n", encoding="utf-8")
    read = [{"kind": "file", "name": saved.name, "path": str(saved)}]
    assert extraction_checks({"extraction": [{"kind": "file", "name": ".csv", "contains": "Norte"}]}, read) == [True]
    assert extraction_checks({"extraction": [{"kind": "file", "name": ".pdf", "contains": "%PDF"}]}, read) == [False]
