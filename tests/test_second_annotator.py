"""The second annotator (eval/second_annotator.py, decided on 13/11/2026): a seeded draw of 25% of each closed
set by page, clean skeletons, both keys judging the same runs, and Cohen's kappa."""
import json

import pytest

import eval.plan_run as pr
import eval.second_annotator as sa


def test_the_allocation_gives_each_page_its_share_and_the_set_25_percent():
    assert sum(sa.allocation({"a": 14, "b": 14, "c": 14}).values()) == 11            # 42 tasks: 10.5, half up
    assert sa.allocation({"a": 4, "b": 4, "c": 2}) == {"a": 1, "b": 1, "c": 1}       # 2.5 -> 3, remainders decide
    assert sum(sa.allocation({f"p{i}": 8 for i in range(10)}).values()) == 20         # 80 tasks: 20


def test_the_draw_is_seeded_stratified_and_keeps_nothing_of_the_answer_key():
    tasks = [{"id": f"t{i}", "fixture": f"p{i % 4}.html", "request": "x", "language": "pt", "origin": "synthetic",
              "checks": ["secret()"], "allowed": ["y"], "reference": [["click", "z", None]], "expected": "not_possible",
              "extraction": [{"kind": "text", "contains": "w"}]} for i in range(40)]
    first, again = sa.draw_set("synthetic", tasks), sa.draw_set("synthetic", tasks)
    assert [t["id"] for t in first] == [t["id"] for t in again] and len(first) == 10
    assert {t["fixture"] for t in first} == {f"p{i}.html" for i in range(4)}          # every page has its share
    for t in first:
        assert t["checks"] == [] and t["allowed"] == [] and t["reference"] == []
        assert "expected" not in t and "extraction" not in t and t["request"] == "x"
    assert [t["id"] for t in sa.draw_set("human", tasks)] != [t["id"] for t in first]  # each set its own draw


def test_draw_never_overwrites_a_set_already_drawn(tmp_path, monkeypatch, capsys):
    source = tmp_path / "closed.json"
    source.write_text(json.dumps({"tasks": [{"id": f"t{i}", "fixture": "p.html", "request": "x"} for i in range(8)]}))
    monkeypatch.setattr(sa, "OUT", tmp_path / "second")
    monkeypatch.setattr(sa, "SETS", {"synthetic": (source, False), "human": (tmp_path / "none.json", True)})
    assert sa.draw() == 0
    drawn = (tmp_path / "second" / "synthetic_tasks.json").read_text()
    assert len(json.loads(drawn)["tasks"]) == 2
    sa.draw()
    assert (tmp_path / "second" / "synthetic_tasks.json").read_text() == drawn
    out = capsys.readouterr().out
    assert "already drawn" in out and "no closed set yet" in out and "x" not in out.replace("tasks", "").replace("next", "")


def test_cohen_kappa_matches_the_known_values():
    pairs = [(True, True)] * 20 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 15
    assert sa.cohen_kappa(pairs) == pytest.approx(0.4)          # agreement 0.7, by chance 0.5
    assert sa.cohen_kappa([(True, True), (False, False)]) == 1.0 and sa.cohen_kappa([]) is None


def test_a_drawn_task_is_judged_by_both_keys_on_the_same_page(page, monkeypatch):
    page.set_content("<button onclick=\"this.dataset.done = 1\">Save</button>")
    task = {"id": "t1", "checks": ["document.querySelector('button').dataset.done === '1'"]}
    monkeypatch.setattr(pr, "_SECOND", {"t1": {"checks": ["!document.querySelector('button').dataset.done"]}})
    assert pr.second_key_success(page, task, True, []) == "True"                # nothing clicked: the 2nd key agrees
    page.click("button")
    assert pr.second_key_success(page, task, True, []) == "False"
    assert pr.second_key_success(page, {"id": "other", "checks": []}, True, []) == ""
    monkeypatch.setattr(pr, "_SECOND", {"t1": {"checks": [], "expected": "not_possible"}})
    assert pr.second_key_success(page, task, False, []) == "True"               # impossible: right not to claim it


def test_kappa_reads_the_runs_judged_by_both_keys(tmp_path, capsys):
    rows = "origin,executor,profile,success,success_2\n" + "synthetic,anchor,s,True,True\n" * 3 + \
           "synthetic,anchor,s,False,False\n" * 2 + "synthetic,anchor,s,True,\n"
    f = tmp_path / "plans_FINAL.csv"
    f.write_text(rows)
    assert sa.main(["kappa", str(f)]) == 0
    out = capsys.readouterr().out
    assert "all" in out and "    5 " in out and "1.000" in out
