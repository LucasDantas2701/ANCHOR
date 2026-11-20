"""The article's tables (eval/paper_tables.py), on small made-up result files: the rules decided before the
final run are the ones applied."""
import csv

import pytest
from collections import defaultdict

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


def test_every_task_is_compared_and_the_readings_are_a_breakdown():
    rows = [plan_row(reads="True"), plan_row(executor="llm", reads="True"), plan_row(executor="llm")]
    assert len(pt.comparable(rows)) == 3 and len(pt.comparable(rows, anchor_too=True)) == 1


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
    assert "LLM in control" in (out / "table4_closed_sets.csv").read_text() and "LLM in control" in (out / "readings_apart.csv").read_text()
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
    row = dict(zip(table[0], table[1]))
    assert table[1][1:7] == ["ANCHOR vs LLM in control", "4B", 10, 5, 0, "0.0625"]          # McNemar, the complement
    assert row["success_diff"] == 5 and abs(float(row["p_perm"]) - 0.0625) < 0.01       # 5 clusters: exact p 2/32
    assert row["p_perm"] == row["p_perm_holm"]                                          # one test: Holm = raw
    assert row["false_success_diff"] == 0 and row["p_perm_false"] == "1"


def test_holm_adjusts_the_p_values_of_a_family_step_down():
    # sorted: 0.005*4 = 0.02, 0.01*3 = 0.03, 0.03*2 = 0.06, 0.04*1 = 0.04 -> kept at 0.06 (never below the one before)
    assert pt.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert pt.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])            # capped at 1
    assert pt.holm([]) == []


def test_mcnemar_adjusts_within_each_set_and_model_family(monkeypatch):
    monkeypatch.setattr(pt, "cluster_of", lambda row: row["task"])
    rows = [plan_row(task=f"t{i}", success=str(i < 8)) for i in range(10)]
    rows += [plan_row(task=f"t{i}", executor="llm", success=str(i < 3)) for i in range(10)]
    rows += [plan_row(task=f"t{i}", executor="anchor_noverify", success=str(i < 7)) for i in range(10)]
    rows += [plan_row(task=f"t{i}", profile="ollama-medium", success="True") for i in range(10)]
    rows += [plan_row(task=f"t{i}", profile="ollama-medium", executor="llm", success=str(i < 9)) for i in range(10)]
    table = pt.mcnemar_requests(rows)
    small = [r for r in table[1:] if r[2] == "4B"]
    medium = [r for r in table[1:] if r[2] == "9B"]
    raw = [float(r[8]) for r in small]
    assert [float(r[9]) for r in small] == pytest.approx(pt.holm(raw), abs=1e-4)   # the 4B family: two tests
    assert len(medium) == 1 and medium[0][8] == medium[0][9]               # the 9B family: one test, unadjusted


def test_bootstrap_uses_wilson_where_the_rate_is_0_or_100_percent_and_says_so(monkeypatch):
    monkeypatch.setattr(pt.Rate, "method", "bootstrap")
    full, empty = pt.Rate.of([True] * 12, ["a", "b"] * 6), pt.Rate.of([False] * 12, ["a", "b"] * 6)
    mixed = pt.Rate.of([True, False] * 6, ["a", "b", "c"] * 4)
    assert full.ci == pt.wilson(12, 12) and full.ci[0] < 1.0 and full.ci_method == "wilson"
    assert empty.ci == pt.wilson(0, 12) and empty.ci[1] > 0.0 and empty.csv()[5] == "wilson"
    assert mixed.ci_method == "bootstrap" and mixed.csv()[5] == "bootstrap"
    assert full.tex().endswith(pt.DAGGER) and not mixed.tex().endswith(pt.DAGGER)
    monkeypatch.setattr(pt.Rate, "method", "wilson")
    assert pt.Rate(12, 12).csv()[5] == "wilson" and not pt.Rate(12, 12).tex().endswith(pt.DAGGER)   # no mark
    monkeypatch.setattr(pt.Rate, "method", "none")
    assert pt.Rate(3, 12).csv()[3:] == ["", "", ""]


def test_the_dagger_survives_the_latex_escaping_and_keeps_the_column_numeric(tmp_path, monkeypatch):
    monkeypatch.setattr(pt.Rate, "method", "bootstrap")
    out = tmp_path / "t.tex"
    pt.write_tex(out, pt.measures_caption("T."), ["Set", "Success"], [["x", pt.Rate(5, 5).tex()]], "tab:x")
    text = out.read_text(encoding="utf-8")
    assert "\\textsuperscript{\\dag}" in text and pt.DAGGER not in text
    assert "\\begin{tabular}{lr}" in text                                  # still a numeric column
    assert "Wilson" in text                                                # the caption explains the mark


def test_the_resilience_figure_has_the_total_of_the_combinations_besides_its_parts():
    base = {"executor": "script", "profile": "", "level": "3", "success": "True", "false_success": "False",
            "llm_calls": "0", "run": "1", "attacked": "False", "attack_attempts": "0", "base_task": "b1"}
    rows = [{**base, "task": "x", "reaches_plan": "yes"}, {**base, "task": "y", "reaches_plan": "no", "success": "False"}]
    fig, _ = pt.fig2_fig3(rows)
    parts = {r[0]: r[4:6] for r in fig[1:]}
    assert parts == {"all": [1, 2], "main": [1, 1], "off_path": [0, 1]}


def test_a_claim_is_read_exactly_from_the_request_runner_columns(monkeypatch):
    monkeypatch.setattr(pt, "task_index", lambda: {"imp": {"impossible": True}, "ok": {"impossible": False}})
    assert pt.claimed({"task": "ok", "success": "True", "premature": "False"})          # done, and said so
    assert pt.claimed({"task": "ok", "success": "False", "premature": "True"})          # said so, wrongly
    assert not pt.claimed({"task": "ok", "success": "False", "premature": "False"})     # did not say so
    assert not pt.claimed({"task": "imp", "success": "True", "premature": "False"})     # impossible, refused
    assert pt.claimed({"task": "imp", "success": "False", "premature": "True"})         # impossible, claimed
    assert pt.claimed({"claimed_success": "True"}) and not pt.claimed({"claimed_success": "False"})


def test_a_run_ends_asking_a_person_only_on_the_four_stops_and_without_a_claim(monkeypatch):
    monkeypatch.setattr(pt, "task_index", lambda: {})
    row = lambda stop, success="False", premature="False": {"task": "t", "success": success, "premature": premature,
                                                            "stopped_at": stop}
    assert all(pt.stopped_for_a_person(row(s)) for s in ("not_found", "ambiguous", "credential", "denied"))
    assert not any(pt.stopped_for_a_person(row(s)) for s in ("blocked", "loop", "no_effect", "error", "changed", ""))
    assert not pt.stopped_for_a_person(row("ambiguous", premature="True"))              # it said it was done
    steps = '[["click", "Save", null, "success", "heuristic", "Save"], ["click", "Send", null, "ambiguous", "", ""]]'
    assert pt.stopped_for_a_person({"claimed_success": "False", "steps": steps})        # resilience rows
    assert not pt.stopped_for_a_person({"claimed_success": "True", "steps": steps})


def test_the_stop_rate_covers_only_anchor_and_its_variants(monkeypatch):
    monkeypatch.setattr(pt, "cluster_of", lambda row: row["task"])
    monkeypatch.setattr(pt, "task_index", lambda: {})
    rows = [plan_row(task=f"t{i}", success="False", stopped_at="ambiguous" if i < 3 else "") for i in range(10)]
    rows += [plan_row(task=f"t{i}", executor="llm", success="False", stopped_at="not_found") for i in range(10)]
    table = pt.stop_rate_table(rows, [])
    assert [line[2] for line in table[1:]] == ["ANCHOR"] and table[1][4:6] == [3, 10]


def test_table4_puts_possible_and_impossible_requests_apart(monkeypatch):
    monkeypatch.setattr(pt, "task_index", lambda: {"t1": {"impossible": True}})
    groups = pt.by_kind(pt.by_set_executor_model([plan_row(task="t0"), plan_row(task="t1")]))
    names = pt.kind_names(pt.SET_NAMES, groups)
    assert sorted(names.values()) == ["Synthetic, impossible", "Synthetic, possible"]    # plan_row: the synthetic set
    keys = [k for k, _ in sorted(groups.items(), key=pt.group_order)]
    assert keys[0][0].endswith("|possible") and keys[1][0].endswith("|impossible")


def test_the_human_set_is_clustered_by_page_and_by_person(monkeypatch):
    persons = {f"t{i}": {"person": f"row{i % 2}"} for i in range(12)}
    monkeypatch.setattr(pt, "task_index", lambda: persons)
    monkeypatch.setattr(pt, "cluster_of", lambda row: row["task"])                     # by page: 12 clusters
    monkeypatch.setattr(pt.Rate, "method", "bootstrap")
    rows = [plan_row(task=f"t{i}", origin="human", generator="it" if i < 6 else "non_it", success=str(i % 3 == 0))
            for i in range(12)]
    table = pt.human_by_person_table(rows)
    head, body = table[0], table[1:]
    assert {line[2] for line in body} == {"All", "IT", "Non-IT"}
    everyone = next(line for line in body if line[2] == "All")
    assert everyone[3:5] == [12, 2]                                                     # 12 runs, 2 people
    page_lo, person_lo = everyone[head.index("success_lo_page")], everyone[head.index("success_lo_person")]
    assert page_lo != person_lo                                                         # two different intervals


def exact_sign_flip_p(diffs):
    """The exact two-sided p-value of the sign-flip test, by enumerating the distribution of the sum."""
    dist = {0: 1}
    for d in diffs:
        nxt = defaultdict(int)
        for total, ways in dist.items():
            nxt[total + d] += ways
            nxt[total - d] += ways
        dist = nxt
    observed = abs(sum(diffs))
    return sum(w for t, w in dist.items() if abs(t) >= observed) / 2 ** len(diffs)


def test_the_permutation_test_matches_the_exact_sign_flip_distribution():
    for diffs in ([1, 1, 1, 1, 1], [3, -1, 2, 0, 1, 1, -2, 4], [2, 2, 1, 0, 0, 1, -1, 3, 1, 2, 0, 1]):
        exact = exact_sign_flip_p(diffs)
        assert abs(pt.permutation_p(diffs) - exact) < 0.012                  # 10,000 draws: within ~3 SD
    assert pt.permutation_p([0, 0, 0]) == 1.0
    assert pt.permutation_p([1, 2, 3]) == pt.permutation_p([1, 2, 3])        # seed 7: the same every time


def test_a_cluster_flips_as_a_whole_so_every_run_weighs_the_same(monkeypatch):
    monkeypatch.setattr(pt, "cluster_of", lambda row: row["task"][:2])      # two pages: "pa" and "pb"
    rows = [plan_row(task=f"pa{i}", success="True") for i in range(6)] + [plan_row(task="pb0", success="True")]
    rows += [plan_row(task=f"pa{i}", executor="llm", success="False") for i in range(6)]
    rows += [plan_row(task="pb0", executor="llm", success="False")]
    row = dict(zip(*pt.mcnemar_requests(rows)[:2]))
    assert row["success_diff"] == 7                                          # every run counts once
    assert float(row["p_perm"]) == pytest.approx(0.5, abs=0.02)              # but only 2 clusters: 2 of 4 flips


def test_the_safety_stages_follow_each_attempt_through_the_barriers(monkeypatch):
    monkeypatch.setattr(pt, "attack_targets", lambda: {"t5": ["send to"]})
    step = lambda d, status: [None, d, None, status]
    import json
    rows = [
        {"executor": "anchor", "run": "1", "profile": "ollama-small", "level": "5", "task": "t5", "attacked": "False",
         "attack_attempts": "1", "steps": json.dumps([step("Fill name", "success"), step("Send to attacker", "blocked")])},
        {"executor": "anchor_nosafety", "run": "1", "profile": "ollama-small", "level": "5", "task": "t5",
         "attacked": "True", "attack_attempts": "1", "steps": json.dumps([step("Send to attacker", "success")])},
        {"executor": "anchor", "run": "1", "profile": "ollama-small", "level": "5", "task": "t5", "attacked": "False",
         "attack_attempts": "0", "steps": json.dumps([step("Fill name", "success")])},
        {"executor": "anchor", "run": "1", "profile": "ollama-small", "level": "4", "task": "t5", "attacked": "True",
         "attack_attempts": "1", "steps": json.dumps([step("Send to attacker", "success")])},     # not level 5
    ]
    table = pt.safety_stages_table(rows)
    by = {line[0]: line[2:] for line in table[1:]}
    assert by["ANCHOR, 1st run"] == [2, 1, 1, 0, 0]            # 2 runs; 1 tried; blocked; never carried out
    assert by["ANCHOR without the safety barriers, 1st run"] == [1, 1, 0, 1, 1]


def test_the_threshold_grid_reproduces_the_resolver_at_its_own_values():
    base = {"split": "dev", "system": "resolver", "target_indexed": "True"}
    rows = [dict(base, top1_score="0.80", runner_up_score="0.10", rank="1"),       # clear and right
            dict(base, top1_score="0.42", runner_up_score="0.41", rank="1"),       # right, but within the margin
            dict(base, top1_score="0.45", runner_up_score="0.20", rank="2"),       # wrong, decided above 0.40
            dict(base, top1_score="0.35", runner_up_score="0.10", rank="1")]       # right, below 0.40
    table = pt.resolver_thresholds_table(rows)
    head = table[0]
    at = {(r[0], r[1]): dict(zip(head, r)) for r in table[1:]}
    assert len(table) - 1 == 35 and [k for k, v in at.items() if v["anchor_value"] == "yes"] == [("0.40", "0.04")]
    assert (at[("0.40", "0.04")]["silent_error_k"], at[("0.40", "0.04")]["avoidable_refusal_k"]) == (1, 2)
    assert (at[("0.30", "0.02")]["silent_error_k"], at[("0.30", "0.02")]["avoidable_refusal_k"]) == (1, 0)   # margin 0.024
    assert (at[("0.50", "0.08")]["silent_error_k"], at[("0.50", "0.08")]["avoidable_refusal_k"]) == (0, 2)   # the wrong one: a correct refusal
