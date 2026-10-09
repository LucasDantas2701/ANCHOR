"""Tables and lists: finding, naming, choosing, saving, and the agent's extract_table."""

import csv
from pathlib import Path

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.tables import TableData, find_tables, match_table, save_csv
from anchor.planner import Plan, Step

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def open_report(page, name="report.html"):
    page.goto((FIXTURES / name).as_uri())
    return find_tables(page)


def test_tables_and_lists_are_found_with_their_names_and_menus_are_left_out(page):
    tables = open_report(page)
    assert [(t.kind, t.name) for t in tables] == [
        ("table", "Vendas por região"), ("table", "Metas do trimestre"), ("list", "Pendências")]
    assert tables[0].headers == ["Região", "Pedidos", "Receita"] and tables[0].rows[0] == ["Norte", "412", "R$ 61.800"]
    assert tables[1].headers == ["Meta", "Responsável", "Situação"] and len(tables[1].rows) == 3   # header row in the body
    assert tables[2].rows == [["Revisar contrato do fornecedor"], ["Aprovar orçamento de outubro"],
                              ["Enviar relatório à diretoria"]]


def test_the_description_picks_a_table_by_name_or_by_its_columns(page):
    tables = open_report(page)
    assert match_table(tables, "exporte a tabela de vendas por região")[0].name == "Vendas por região"
    assert match_table(tables, "a tabela de receita")[0].name == "Vendas por região"          # a column
    assert match_table(tables, "lista de pendências")[0].name == "Pendências"
    best, candidates = match_table(tables, "a tabela")                                       # names none
    assert best is None and len(candidates) == 3


def test_a_single_table_needs_no_name(page):
    page.set_content("<h2>Clientes</h2><table><tr><th>Nome</th></tr><tr><td>Ana</td></tr><tr><td>Bia</td></tr></table>")
    assert match_table(find_tables(page), "extraia a tabela")[0].name == "Clientes"


def test_tables_without_headers_get_numbered_columns_and_short_rows_are_padded(tmp_path):
    table = TableData(kind="table", name="Sem cabeçalho", headers=[], rows=[["a", "b", "c"], ["d"]])
    assert table.columns == ["column 1", "column 2", "column 3"]
    path = save_csv(table, tmp_path, ";")
    rows = list(csv.reader(path.open(encoding="utf-8-sig"), delimiter=";"))
    assert rows == [["column 1", "column 2", "column 3"], ["a", "b", "c"], ["d", "", ""]]
    assert path.name.startswith("sem-cabecalho_") and save_csv(table, tmp_path, ";") != path   # never overwritten


class OnePlan:
    def __init__(self, *steps):
        self.steps, self.calls, self.histories = list(steps), 0, []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.calls += 1
        self.histories.append(list(history or []))
        return Plan(steps=[Step(*s) for s in self.steps] if self.calls == 1 else [])


def test_the_agent_saves_the_table_as_csv_and_keeps_what_was_read(page, tmp_path):
    page.goto((FIXTURES / "report_en.html").as_uri())
    result = Agent(page, OnePlan(("extract_table", "Sales by region", None), ("extract_text", "Total revenue", None)),
                   ActionExecutor(page), report=None, output_dir=tmp_path).run("export the sales by region table")
    assert result.ok, result.message
    table, text = result.extractions
    assert table["kind"] == "table" and table["rows"] == 4 and table["columns"] == ["Region", "Orders", "Revenue"]
    rows = list(csv.reader(Path(table["path"]).open(encoding="utf-8-sig")))
    assert rows[1] == ["North", "412", "$61,800"]
    assert text["kind"] == "text" and "182,400" in text["text"]


def test_an_unclear_table_fails_with_the_names_for_the_planner(page, tmp_path):
    page.goto((FIXTURES / "report.html").as_uri())
    planner = OnePlan(("extract_table", "a tabela", None))
    result = Agent(page, planner, ActionExecutor(page), report=None, output_dir=tmp_path).run("exporte a tabela")
    assert not result.ok and result.records[0].status == "ambiguous"
    history = " ".join(" ".join(h) for h in planner.histories)
    assert "Vendas por região" in history and "Pendências" in history


def test_the_page_summary_lists_the_tables_at_the_end(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    page.goto((FIXTURES / "report.html").as_uri())
    lines = page_elements(ElementResolver(page), request="exporte as vendas", language="pt")
    assert lines[-3:] == ['Tabela "Vendas por região" [colunas: Região | Pedidos | Receita; 4 linhas]',
                          'Tabela "Metas do trimestre" [colunas: Meta | Responsável | Situação; 3 linhas]',
                          'Lista "Pendências" [3 itens]']


def test_pages_without_tables_get_the_same_summary(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    page.goto((FIXTURES / "registration.html").as_uri())
    lines = page_elements(ElementResolver(page), request="cadastre", language="pt")
    assert not any(line.startswith(('Tabela "', 'Lista "')) for line in lines)   # not: Lista de opções
