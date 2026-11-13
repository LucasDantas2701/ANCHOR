"""The article's tables (eval/paper_tables.py), on small made-up result files: the rules decided before the
final run are the ones applied."""
import csv

import pytest

import eval.paper_tables as pt


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    return path


def plan_row(**kw):
    row = {"profile": "ollama-small", "task": "t-1", "split": "test", "origin": "", "generator": "", "language": "pt",
           "success": "False", "premature": "False", "clean": "False", "stopped_at": "", "plan_valid": "True",
           "executor": "anchor", "reads": "False"}
    row.update(kw)
    row["_file"] = "plans_x.csv"
    return row


def test_wilson_matches_the_known_values_and_handles_the_edges():
    lo, hi = pt.wilson(27, 30)
    assert round(lo, 3) == 0.744 and round(hi, 3) == 0.965
    assert pt.wilson(0, 30)[0] == 0.0 and pt.wilson(30, 30)[1] == 1.0 and pt.wilson(0, 0) is None


@pytest.mark.parametrize("stop, valid, cause", [
    ("denied", "True", "safety stop"), ("blocked", "True", "safety stop"), ("changed", "True", "safety stop"),
    ("not_found", "True", "element resolution"), ("ambiguous", "True", "element resolution"),
    ("no_effect", "True", "effect verification"), ("wrong_effect", "True", "effect verification"),
    ("", "True", "planning"), ("", "False", "planning"), ("failed", "True", "other"), ("no_such_file", "True", "other")])
def test_the_failure_rule_is_applied_in_its_order(stop, valid, cause):
    assert pt.failure_cause(plan_row(stopped_at=stop, plan_valid=valid)) == cause


def test_table6_counts_each_failure_once_and_the_false_successes_apart():
    rows = [plan_row(stopped_at="not_found"), plan_row(premature="True"), plan_row(success="True"),
            plan_row(executor="llm", premature="True", stopped_at="failed")]
    t = {r[0]: r[1:] for r in pt.table6(rows)}
    # columns: ANCHOR / ollama-small, then LLM in control / ollama-small
    assert t["Element resolution"] == [1, 0] and t["Planning"] == [1, 0] and t["Other"] == [0, 1]
    assert t["Of which false success"] == [1, 1] and t["Failed runs"] == [2, 1] and t["Runs"] == [3, 1]
    assert pt.table6(rows)[0] == ["Cause", "ANCHOR 4B", "LLM 4B"]


def test_the_model_in_control_is_compared_without_the_tasks_that_expect_readings():
    rows = [plan_row(reads="True"), plan_row(executor="llm", reads="True"), plan_row(executor="llm")]
    assert len(pt.comparable(rows)) == 2 and len(pt.comparable(rows, anchor_too=True)) == 1


def test_resilience_parts_and_the_second_run_without_a_model_call():
    base = {"executor": "anchor", "profile": "ollama-small", "level": "2", "success": "True", "false_success": "False",
            "llm_calls": "0", "run": "2", "reaches_plan": "yes", "attacked": "False", "attack_attempts": "0"}
    rows = [base, {**base, "llm_calls": "1"}, {**base, "reaches_plan": "no"}, {**base, "reaches_plan": ""}]
    fig, _ = pt.fig2_fig3(rows)
    main = next(r for r in fig[1:] if r[0] == "main")
    off = next(r for r in fig[1:] if r[0] == "off_path")
    assert main[1] == "ANCHOR, 2nd run (no model call)" and main[4:6] == [2, 3]   # the one with a model call fails
    assert off[4:6] == [1, 1]


def test_the_command_writes_every_table_and_names_its_sources(tmp_path):
    plans = write(tmp_path / "plans_20261201-100000_abc1234_FINAL.csv", [
        {k: v for k, v in plan_row(success="True", clean="True").items() if k != "_file"},
        {k: v for k, v in plan_row(task="t-ord-a1", success="True").items() if k != "_file"},
        {k: v for k, v in plan_row(origin="synthetic_controlled", generator="chatgpt", task="sy-1").items() if k != "_file"},
        {k: v for k, v in plan_row(origin="human", generator="it", task="hu-1", success="True").items() if k != "_file"},
        {k: v for k, v in plan_row(executor="llm", reads="True").items() if k != "_file"}])
    resolver = write(tmp_path / "20261201-100000_abc1234_FINAL.csv", [
        {"split": "test", "action": "click", "rank": "1", "outcome": "correct", "ms": "10"},
        {"split": "test", "action": "fill", "rank": "", "outcome": "perception_failure", "ms": "12"}])
    out = tmp_path / "out"
    assert pt.main(["--plans", str(plans), "--resolver", str(resolver), "--out", str(out)]) == 0
    for name in ("table4_closed_sets.tex", "sensitivity.csv", "table5_people_vs_ai.csv", "table6_failures.tex",
                 "table7_elements.csv", "readings_apart.csv", "sources.txt"):
        assert (out / name).exists(), name
    sens = (out / "sensitivity.csv").read_text(encoding="utf-8")
    assert "without t-ord-a1 and t-ord-c1" in sens and "without ChatGPT" not in sens     # the ChatGPT one has no other row
    t5 = (out / "table5_people_vs_ai.csv").read_text(encoding="utf-8")
    assert "controlled, all" in t5 and "human, IT" in t5 and "controlled, without ChatGPT" not in t5
    assert "readings" not in (out / "table4_closed_sets.csv").read_text() and "LLM in control" in (out / "readings_apart.csv").read_text()
    t7 = list(csv.reader(open(out / "table7_elements.csv")))
    assert t7[1][:3] == ["All", "2", "50.0"] and t7[1][-1] == "50.0" and t7[3][0] == "type"
    assert "abc1234" in (out / "sources.txt").read_text()


def test_final_mode_refuses_files_from_different_commits(tmp_path, monkeypatch):
    monkeypatch.setattr(pt, "RESULTS", tmp_path)
    write(tmp_path / "plans_20261201-100000_abc1234_FINAL.csv", [{k: v for k, v in plan_row().items() if k != "_file"}])
    write(tmp_path / "20261201-100000_def5678_FINAL.csv", [{"split": "test", "action": "click", "rank": "1", "outcome": "correct", "ms": "1"}])
    with pytest.raises(SystemExit):
        pt.main(["--final", "--out", str(tmp_path / "o")])



def test_the_latex_follows_the_articles_style(tmp_path):
    """No booktabs; \\hline\\hline at the top and bottom; \\small; table* above 5 columns; l for text, r for numbers;
    4B and 9B; percent signs escaped; the labels unchanged."""
    rows = [{k: v for k, v in plan_row(success="True", clean="True").items() if k != "_file"},
            {k: v for k, v in plan_row(profile="ollama-medium").items() if k != "_file"}]
    plans = write(tmp_path / "plans_x.csv", rows)
    resolver = write(tmp_path / "r.csv", [{"split": "test", "action": "extract_text", "rank": "1", "outcome": "correct", "ms": "9"}])
    out = tmp_path / "out"
    pt.main(["--plans", str(plans), "--resolver", str(resolver), "--out", str(out)])
    t4 = (out / "table4_closed_sets.tex").read_text(encoding="utf-8")
    assert "booktabs" not in t4 and "toprule" not in t4 and t4.count("\\hline\\hline") == 2 and "\\small" in t4
    assert "\\begin{table*}" in t4 and "\\begin{tabular}{lllrrrr}" in t4 and "\\label{tab:closed-sets}" in t4
    assert "& 4B &" in t4 and "& 9B &" in t4 and "ollama" not in t4 and "95\\% Wilson" in t4
    assert "Success & False success & No extra steps & n" in t4
    t6 = (out / "table6_failures.tex").read_text(encoding="utf-8")
    assert "\\begin{table}[ht]" in t6 and "\\begin{tabular}{lrr}" in t6 and "\\multicolumn{2}{c}{ANCHOR}" in t6
    t7 = (out / "table7_elements.tex").read_text(encoding="utf-8")
    assert "\\begin{table*}" in t7 and "read text" in t7 and "extract" not in t7 and "_" not in t7.split("\\label")[0].split("caption")[1]
    assert "R@1 & R@3" in t7 and "Silent" in t7 and "lo" not in t7.split("\\hline")[2]


def test_mcnemar_exact_matches_the_binomial_values():
    assert pt.mcnemar_exact(0, 0) == 1.0
    assert pt.mcnemar_exact(5, 0) == pytest.approx(0.0625)            # 2 x (1/2)^5
    assert pt.mcnemar_exact(6, 1) == pytest.approx(0.125)             # 2 x (1 + 7) / 2^7
    assert pt.mcnemar_exact(3, 3) == 1.0


def test_the_clustered_bootstrap_is_fixed_by_its_seed_and_wider_when_runs_share_a_cluster():
    outcomes = [True] * 10 + [False] * 10
    one_each = [str(i) for i in range(20)]
    by_page = ["a"] * 10 + ["b"] * 10                                  # all the successes on one page
    first, again = pt.bootstrap(outcomes, by_page, samples=2000), pt.bootstrap(outcomes, by_page, samples=2000)
    assert first == again
    narrow = pt.bootstrap(outcomes, one_each, samples=2000)
    assert (first[1] - first[0]) > (narrow[1] - narrow[0])
    assert pt.bootstrap([], []) is None


def test_a_page_is_known_when_it_or_its_origin_was_used_in_development():
    known = {"registration.html", "store.html"}
    assert pt.page_kind("registration.html", known) == "known" and pt.page_kind("holdout_blog.html", known) == "new"
    assert pt.page_kind("collection/cadastro.html", known) == "known"           # made from registration.html
    assert pt.page_kind("collection/reservas.html", known) == "new"             # made from holdout_booking.html
    assert pt.page_kind("resilience_closed/L3/store.html", known) == "known"


def test_mcnemar_pairs_anchor_with_each_system_task_by_task(monkeypatch):
    monkeypatch.setattr(pt, "cluster_of", lambda row: row["task"])
    rows = [plan_row(task=f"t{i}", success=str(i < 8)) for i in range(10)]
    rows += [plan_row(task=f"t{i}", executor="llm", success=str(i < 3)) for i in range(10)]
    table = pt.mcnemar_requests(rows)
    assert table[1][1:] == ["ANCHOR vs LLM in control", "4B", 10, 5, 0, "0.0625"]


def test_the_resilience_figure_has_the_total_of_the_combinations_besides_its_parts():
    base = {"executor": "script", "profile": "", "level": "3", "success": "True", "false_success": "False",
            "llm_calls": "0", "run": "1", "attacked": "False", "attack_attempts": "0", "base_task": "b1"}
    rows = [{**base, "task": "x", "reaches_plan": "yes"}, {**base, "task": "y", "reaches_plan": "no", "success": "False"}]
    fig, _ = pt.fig2_fig3(rows)
    parts = {r[0]: r[4:6] for r in fig[1:]}
    assert parts == {"all": [1, 2], "main": [1, 1], "off_path": [0, 1]}
