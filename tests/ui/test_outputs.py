"""What a run brings back, in the interface: answers, tables, files and a screenshot when asked."""
from types import SimpleNamespace

from anchor.ui.execute import PREVIEW_ROWS, run_outputs, wants_screenshot


def test_a_screenshot_is_asked_in_the_form_or_in_the_requests_words():
    assert wants_screenshot({"screenshot": True}, "busque vagas")
    for words in ("pesquise vagas e me mande um print", "tire uma captura de tela do resultado", "search jobs and take a screenshot"):
        assert wants_screenshot({}, words)
    assert not wants_screenshot({}, "pesquise vagas de RPA e me mande a lista")


def test_the_outputs_have_the_answers_the_tables_first_rows_the_files_and_the_screenshot(page, tmp_path):
    csv_file = tmp_path / "vagas.csv"
    csv_file.write_text("cargo;empresa\n" + "".join(f"Dev {i};Empresa {i}\n" for i in range(80)), encoding="utf-8-sig")
    result = SimpleNamespace(extractions=[
        {"kind": "text", "description": "o salário", "text": "R$ 5.000"},
        {"kind": "table", "description": "a tabela de vagas", "name": "Vagas", "rows": 80, "columns": ["cargo", "empresa"], "path": str(csv_file)},
        {"kind": "file", "description": "o edital", "name": "edital.pdf", "bytes": 1234, "path": str(tmp_path / "edital.pdf")}])
    page.set_content("<h1>Vagas</h1>")
    out = run_outputs(result, page, screenshot=True, folder=tmp_path / "out", tag="7")
    assert [o["kind"] for o in out] == ["text", "table", "file", "screenshot"]
    table = out[1]
    assert table["columns"] == ["cargo", "empresa"] and len(table["rows"]) == PREVIEW_ROWS and table["total"] == 80
    assert table["rows"][0] == ["Dev 0", "Empresa 0"]
    shot = tmp_path / "out" / "screenshot-7.png"
    assert out[3]["path"] == str(shot) and shot.read_bytes()[:4] == b"\x89PNG"
    assert [o["kind"] for o in run_outputs(result, page, screenshot=False, folder=tmp_path)] == ["text", "table", "file"]


def test_only_a_file_listed_in_a_runs_outputs_is_served(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.runs import Job
    from anchor.ui.server import create_app

    from .test_runs import HEADERS, PORT
    shot = tmp_path / "screenshot-1.png"
    shot.write_bytes(b"\x89PNG fake")
    secret = tmp_path / "secret.txt"
    secret.write_text("no")
    app = create_app(tmp_path / "a", token="the-code", port=PORT, runner=lambda job: {}, headless=True)
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    job = Job(id=5, kind="request", title="x", spec={}, state="checked",
              result={"state": "checked", "outputs": [{"kind": "screenshot", "path": str(shot)}],
                      "rows": [{"number": 2, "outputs": [{"kind": "text", "text": "x"}]}]})
    app.state.runs.jobs[5] = job
    assert c.get("/api/runs/5/outputs/0", headers=HEADERS).content == b"\x89PNG fake"
    assert c.get("/api/runs/5/outputs/1", headers=HEADERS).status_code == 404                 # not listed
    assert c.get("/api/runs/5/outputs/0", params={"row": 2}, headers=HEADERS).status_code == 404  # a text has no file
    assert c.get("/api/runs/5/outputs/0").status_code == 401                                   # the access code
