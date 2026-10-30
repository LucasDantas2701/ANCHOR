"""Spreadsheets for automations: CSV and .xlsx read as a person typed them, checked before running."""
import base64
from datetime import date, datetime
from io import BytesIO

import pytest

from anchor.automations.params import ParameterError, cell_text, check_rows, rows_from_file


def xlsx(rows) -> bytes:
    from openpyxl import Workbook
    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def test_a_csv_from_excel_in_brazil_and_a_utf8_one_read_the_same():
    utf8 = "nome;cpf\nMaria Silva;123\nJoão;456\n".encode("utf-8-sig")
    windows = "nome;cpf\nMaria Silva;123\nJoão;456\n".encode("cp1252")
    assert rows_from_file(utf8, "a.csv") == rows_from_file(windows, "a.csv") == [{"nome": "Maria Silva", "cpf": "123"}, {"nome": "João", "cpf": "456"}]


def test_an_xlsx_gives_cells_as_a_person_would_type_them_and_skips_empty_rows():
    data = xlsx([["nome", "idade", "nascimento", None], ["Maria", 30.0, datetime(1996, 5, 4), None], [None, None, None, None],
                 ["Ana", 41, date(1985, 1, 2), None]])
    assert rows_from_file(data, "pessoas.xlsx") == [{"nome": "Maria", "idade": "30", "nascimento": "1996-05-04"},
                                                    {"nome": "Ana", "idade": "41", "nascimento": "1985-01-02"}]
    assert cell_text(12.5) == "12.5" and cell_text(None) == ""


def test_other_files_and_broken_workbooks_are_refused():
    with pytest.raises(ParameterError):
        rows_from_file(b"x", "a.pdf")
    with pytest.raises(ParameterError):
        rows_from_file(b"not a workbook", "a.xlsx")


def test_the_check_names_missing_and_extra_columns_and_rows_with_an_empty_value():
    rows = [{"nome": "Maria", "obs": "x"}, {"nome": "", "obs": "y"}]
    checked = check_rows(["nome", "cpf"], rows)
    assert checked["missing"] == ["cpf"] and checked["extra"] == ["obs"] and checked["blank_rows"] == [2] and checked["rows"] == 2


# --- through the interface ----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.automations.model import Automation, AutomationStore
    from anchor.ui.server import create_app
    from tests.ui.test_runs import PORT
    store = AutomationStore(tmp_path / "automations")
    store.create(Automation(name="cadastro", request="cadastre {nome} com o CPF {cpf}", url="https://example.com", profile="ollama-small"))
    app = create_app(store.root, token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""}, headless=True)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def test_the_interface_checks_a_spreadsheet_and_runs_only_complete_rows(client):
    from tests.ui.test_runs import HEADERS
    data = xlsx([["nome", "cpf", "setor"], ["Maria", "123", "TI"], ["Ana", "456", "RH"]])
    checked = client.post("/api/automations/cadastro/sheet", json={"filename": "p.xlsx", "content": base64.b64encode(data).decode()},
                          headers=HEADERS).json()
    assert checked["rows"] == 2 and checked["missing"] == [] and checked["extra"] == ["setor"] and len(checked["preview"]) == 2
    ok = client.post("/api/runs", json={"kind": "automation", "name": "cadastro", "rows": checked["all"]}, headers=HEADERS)
    assert ok.status_code == 200
    blank = client.post("/api/runs", json={"kind": "automation", "name": "cadastro", "rows": [{"nome": "Maria", "cpf": ""}]}, headers=HEADERS)
    assert blank.status_code == 400 and "empty value: 1" in blank.json()["detail"]
    missing = client.post("/api/runs", json={"kind": "automation", "name": "cadastro", "rows": [{"nome": "Maria"}]}, headers=HEADERS)
    assert missing.status_code == 400 and "cpf" in missing.json()["detail"]


def test_each_row_runs_a_failure_does_not_stop_the_others_and_stopping_ends_the_rest(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import anchor.ui.execute as execute
    from anchor.automations.model import Automation, AutomationStore
    from anchor.ui.runs import Job, RunStopped
    store = AutomationStore(tmp_path / "a")
    automation = store.create(Automation(name="c", request="cadastre {nome}", url="https://example.com", profile="ollama-small"))
    seen = []

    def fake_run(store, name, page, executor, make_planner, params, **kw):
        seen.append(params["nome"])
        if params["nome"] == "erro":
            raise ValueError("boom")
        if params["nome"] == "parar":
            raise RunStopped()
        result = SimpleNamespace(ok=params["nome"] != "falha", denied=False, status="success", message=f"fez {params['nome']}",
                                 records=[SimpleNamespace(status="success")], seconds=1.0, llm_calls=0)
        return result, "replay", "r"

    monkeypatch.setattr(execute, "run_automation", fake_run)
    page = SimpleNamespace(goto=lambda url: None)
    rows = [{"nome": n} for n in ("Ana", "falha", "erro", "Bia", "parar", "Caio")]
    job = Job(id=1, kind="automation", title="c", spec={"name": "c", "rows": rows})
    out = execute.Executor(store, headless=True)._rows(job, store, "c", automation, page, None, None)
    assert seen == ["Ana", "falha", "erro", "Bia", "parar"]                              # Caio never ran
    assert [r["state"] for r in out["rows"]] == ["checked", "not_done", "error", "checked", "stopped", "stopped"]
    assert out["state"] == "stopped" and out["message"] == "2 of 6 rows done." and out["rows"][5]["message"].startswith("Not run")
    assert [e["number"] for e in job.events if e["type"] == "row"] == [1, 2, 3, 4, 5]
