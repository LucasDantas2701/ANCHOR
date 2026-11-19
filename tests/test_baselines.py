"""The two element-selection baselines (decided on 19/11/2026): exact accessible name and BM25."""
import eval.baselines as bl
import eval.paper_tables as pt
from eval.run import run_case

PAGE = """<!doctype html><html lang="pt"><body>
<label>Nome <input id="nome"></label><label>E-mail <input id="mail"></label>
<div><p>Pedido 12</p><button id="s">Salvar</button></div>
<div><p>Pedido 13</p><button id="x" aria-label="Excluir pedido">🗑</button></div></body></html>"""


def rec(i, **kw):
    r = {"id": f"el-{i}", "label": "", "text": "", "value": "", "hint": "", "testId": "", "context": "", "role": "button"}
    r.update(kw)
    return r


def test_the_words_are_only_lowercased_and_stripped_of_accents():
    assert bl.words("E-mail Corporativo, Seção") == ["e", "mail", "corporativo", "secao"]   # no compound "email"


def test_the_description_also_counts_without_its_first_word_when_it_names_a_kind_of_element():
    assert bl.query_forms("botão Salvar cadastro") == {"botao salvar cadastro", "salvar cadastro"}
    assert bl.query_forms("campo do Nome") == {"campo do nome", "nome"}
    assert bl.query_forms("Salvar") == {"salvar"}


def test_exact_matches_the_accessible_name_in_the_page_order():
    records = [rec(0, text="Salvar"), rec(1, label="Excluir pedido", text="🗑"), rec(2, text="Salvar")]
    assert [r["id"] for r, _ in bl.rank_exact("botão Salvar", records)] == ["el-0", "el-2"]
    assert [r["id"] for r, _ in bl.rank_exact("botão Excluir pedido", records)] == ["el-1"]   # the label first
    assert bl.rank_exact("botão Gravar", records) == []


def test_bm25_ranks_by_the_rarer_words_and_leaves_out_what_shares_none():
    records = [rec(0, text="Salvar", context="Pedido 12 Salvar"), rec(1, text="Salvar", context="Pedido 13 Salvar"),
               rec(2, label="Excluir pedido", context="Pedido 13")]
    ranked = bl.rank_bm25("Salvar pedido 13", records)
    assert ranked[0][0]["id"] == "el-1" and all(score > 0 for _, score in ranked)
    assert bl.rank_bm25("Imprimir", records) == []


def test_a_baseline_runs_on_the_same_indexed_elements_as_the_resolver(page):
    page.set_content(PAGE)
    suite = {"site": "t", "language": "pt"}
    case = {"id": "c1", "action": "click", "query": "botão Salvar", "expected": "#s"}
    exact, bm25, resolver = (run_case(page, suite, case, b) for b in ("exact", "bm25", None))
    assert (exact.system, bm25.system, resolver.system) == ("exact", "bm25", "resolver")
    assert exact.rank == 1 and exact.status == "success" and exact.n_indexed == resolver.n_indexed
    none = run_case(page, suite, {**case, "query": "botão Gravar"}, "exact")
    assert none.status == "not_found" and none.rank is None and none.outcome == "correct_refusal"


def test_table7_adds_one_row_per_baseline_over_all_cases():
    base = {"split": "dev", "action": "click", "status": "success", "outcome": "correct", "ms": "1"}
    rows = [dict(base, rank="1", system="resolver"), dict(base, rank="2", system="resolver"),
            dict(base, rank="1", system="bm25"), dict(base, rank="", system="exact", outcome="avoidable_refusal")]
    table = pt.table7(rows)
    groups = [line[0] for line in table[1:]]
    assert groups == ["All", "click", "Exact name", "BM25"]
    assert [line[1] for line in table[1:]] == [2, 2, 1, 1]               # the Resolver's rows hold only its cases
