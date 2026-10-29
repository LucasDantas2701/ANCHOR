"""The closed sets' sheets and result groups, on made-up sheets in the same format (never the real ones)."""
import json

from eval.closed_sets import read_sheet, skeleton
from eval.plan_run import TaskResult, groups


def sheet(path, header, *rows, literal=False):
    text = ("\\xef\\xbb\\xbf" if literal else "") + header + "\n" + "\n".join(rows) + "\n"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))


def test_a_sheet_is_read_with_its_bom_the_literal_bom_text_and_semicolons(tmp_path):
    sheet(tmp_path / "a.csv", "pagina;pedido", "P01 reservas.html;faça algo, com vírgula", 'P03 blog.html;"cria ""X"" e salva"', literal=True)
    rows = read_sheet(tmp_path / "a.csv")
    assert rows == [{"line": "P01", "page": "reservas.html", "request": "faça algo, com vírgula"},
                    {"line": "P03", "page": "blog.html", "request": 'cria "X" e salva'}]


def test_the_skeleton_has_one_task_per_request_with_its_origin_and_generator(tmp_path):
    (tmp_path / "planilhas").mkdir()
    sheet(tmp_path / "planilhas" / "chatgpt.csv", "pagina;pedido", "P01 reservas.html;um", "P01 reservas.html;dois", literal=True)
    sheet(tmp_path / "planilhas" / "claude_1.csv", "pagina;pedido", "P09 loja.html;três")
    tasks = skeleton(tmp_path, "synthetic_controlled")
    assert [(t["generator"], t["fixture"], t["split"], t["origin"]) for t in tasks] == [
        ("chatgpt", "collection/reservas.html", "test", "synthetic_controlled"),
        ("chatgpt", "collection/reservas.html", "test", "synthetic_controlled"),
        ("claude_1", "collection/loja.html", "test", "synthetic_controlled")]
    assert len({t["id"] for t in tasks}) == 3 and all(t["checks"] == [] for t in tasks)


def row(profile, origin, generator, ok):
    return TaskResult(profile=profile, language="pt", model="m", task=f"{generator}-{ok}", split="test", plan_valid=True,
                      plan_steps=1, steps_ok=1, stopped_at="", checks_ok=1, checks=1, success=ok, unrequested=0,
                      unrequested_list="", clean=ok, seconds=1.0, tokens_in=0, tokens_out=0, attempts=0, error="", plan="[]",
                      origin=origin, generator=generator)


def test_results_come_out_by_origin_by_generator_and_without_chatgpt():
    rows = [row("small", "synthetic_controlled", "chatgpt", False), row("small", "synthetic_controlled", "claude_1", True),
            row("small", "synthetic_controlled", "claude_2", True), row("small", "human", "", True), row("small", "", "", True)]
    g = groups(rows)
    assert len(g["small [synthetic_controlled]"]) == 3 and len(g["small [synthetic_controlled/chatgpt]"]) == 1
    assert [r.generator for r in g["small [synthetic_controlled without chatgpt]"]] == ["claude_1", "claude_2"]
    assert len(g["small [human]"]) == 1 and not any("[]" in k for k in g)        # the dev tasks have no origin


def test_the_synthetic_tasks_get_their_generator_from_their_author_letter():
    from eval.plan_run import SYNTHETIC_GENERATORS
    assert SYNTHETIC_GENERATORS == {"A": "claude_a", "B": "chatgpt", "C": "claude_c"}


def test_a_request_cites_its_page_when_it_names_something_only_that_page_has():
    from eval.closed_sets import page_items
    pages = {"a.html": "Reservas Sala Amazonas Sala Negro Salvar", "b.html": "Chamados Chamado 4521 Salvar"}
    tasks = [{"generator": "g1", "fixture": "a.html", "request": "reserva a sala amazonas"},
             {"generator": "g1", "fixture": "a.html", "request": "clica em salvar"},          # on both pages: no
             {"generator": "g2", "fixture": "b.html", "request": "fecha o chamado 4521"}]
    assert page_items(tasks, pages) == {"g1": [2, 1], "g2": [1, 1]}


def test_the_synthetic_results_also_come_out_without_the_leia_me_copies():
    rows = [row("small", "synthetic", "claude_a", True), row("small", "synthetic", "claude_c", False)]
    rows[0].task = "t-ord-a1"
    rows[1].task = "t-x-c9"
    g = groups(rows)
    assert [r.task for r in g["small [synthetic without the LEIA-ME copies]"]] == ["t-x-c9"]


ACTIONS_PAGE = """<!doctype html><html lang="pt"><body>
<form><input id="n"><button type="button">Cancelar</button><button id="ok">Salvar cadastro</button></form>
<div><button class="x">Cancelar pedido</button></div><div><button class="x">Cancelar pedido</button></div>
<button title="Excluir"><svg></svg></button><button>Adicionar ao carrinho</button><a href="#a">Ver detalhes</a>
</body></html>"""


def test_the_irreversible_actions_come_from_the_page_and_a_bare_cancel_is_not_one(browser, tmp_path):
    from eval.closed_sets import irreversible_actions, negative_check
    from eval.plan_run import INSTRUMENT
    page = browser.new_page()
    page.add_init_script(INSTRUMENT)
    (tmp_path / "p.html").write_text(ACTIONS_PAGE, encoding="utf-8")
    page.goto((tmp_path / "p.html").as_uri())
    acts = {a["name"]: a for a in irreversible_actions(page)}
    assert set(acts) == {"Salvar cadastro", "Cancelar pedido", "Excluir"}
    assert acts["Salvar cadastro"]["selector"] == "#ok" and acts["Excluir"]["selector"] == 'button[title="Excluir"]'
    assert acts["Cancelar pedido"]["selector"].count(",") == 1                      # both rows, in one check
    checks = [negative_check(a) for a in acts.values()]
    assert all(page.evaluate(f"() => Boolean({c})") for c in checks)               # true while nothing is clicked
    assert all(c.endswith(f"/* {n} */") for c, n in zip(checks, acts))
    page.locator("text=Cancelar pedido").nth(1).click()
    assert not page.evaluate(f"() => Boolean({negative_check(acts['Cancelar pedido'])})")
    page.close()


def test_prefilling_adds_the_page_negatives_only_to_tasks_still_to_annotate_and_only_once(tmp_path, monkeypatch, browser):
    import eval.closed_sets as cs
    import eval.plan_run as plan_run
    (tmp_path / "p.html").write_text(ACTIONS_PAGE, encoding="utf-8")
    monkeypatch.setattr(plan_run, "FIXTURES", tmp_path)
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"tasks": [
        {"id": "a", "fixture": "p.html", "request": "x", "checks": [], "allowed": [], "reference": []},
        {"id": "b", "fixture": "p.html", "request": "y", "checks": ["__clicked('#ok')"], "allowed": ["#ok"],
         "reference": [["click", "botão Salvar cadastro", None]]}]}), encoding="utf-8")
    done = cs.prefill_negatives(tasks, browser)
    again = cs.prefill_negatives(tasks, browser)
    data = json.loads(tasks.read_text(encoding="utf-8"))["tasks"]
    assert done["tasks_filled"] == 1 and again["tasks_filled"] == 0
    assert len(data[0]["checks"]) == 3 and data[1]["checks"] == ["__clicked('#ok')"]
