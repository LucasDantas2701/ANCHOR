"""The closed set's generator, on a made-up base (one made-up page and task), never on the real one."""
import csv
import json
import random
import shutil
from pathlib import Path

import pytest

import eval.plan_run as plan_run
import eval.resilience.closed.generate as gen
import eval.resilience.closed.reference as reference
import eval.resilience.closed.targets as targets_mod

HERE = Path(__file__).parent
TASK = {"base_task": "t1", "id": "t1@L0", "level": 0, "fixture": "resilience/L0/page.html", "request": "salva o cadastro",
        "checks": ["document.body.dataset.sent === '1'"], "allowed": ["[data-eval~=e1]", "[data-eval~=e3]", "[data-eval~=e4]"],
        "reference": [["fill", "Nome completo", "Ana"], ["check", "Aceito os termos", None], ["click", "Salvar cadastro", None]]}
STEPS = [{"action": "fill", "eval": "e1", "value": "Ana"}, {"action": "check", "eval": "e3", "value": None},
         {"action": "click", "eval": "e4", "value": None}]
SYN = {w: [f"{w.lower()}{n}" for n in range(1, 6)] for w in ("Nome", "Salvar", "Abrir", "Setor", "Aceito", "Ver", "Primeiro", "Terceiro")}


@pytest.fixture
def base(tmp_path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    (fixtures / "resilience" / "L0").mkdir(parents=True)
    shutil.copy(HERE / "page.html", fixtures / "resilience" / "L0" / "page.html")
    monkeypatch.setattr(plan_run, "FIXTURES", fixtures)
    monkeypatch.setattr(targets_mod, "base_tasks", lambda: [TASK])
    monkeypatch.setattr(reference, "load_targets", lambda: {"t1": {"steps": STEPS}})
    monkeypatch.setattr(gen, "synonyms", lambda word, pos, lang: SYN.get(word, []))
    monkeypatch.setattr(gen, "nltk_versions", lambda: {"nltk": "test"})
    out = {"pages_out": fixtures / "resilience_closed", "tasks_out": tmp_path / "tasks.json", "gen_out": tmp_path / "generated"}
    return out


def run(base, browser, vetoes=None):
    report = gen.generate(vetoes_path=vetoes, browser=browser, **base)
    tasks = json.loads(base["tasks_out"].read_text(encoding="utf-8"))["tasks"]
    return report, tasks


def test_every_task_and_level_gets_its_operators_is_checked_possible_and_recorded(base, browser):
    report, tasks = run(base, browser)
    assert len(report["slots"]) == 5 and all(s["possible"] for s in report["slots"])
    assert [t["id"] for t in tasks] == [f"t1@C{lv}" for lv in range(1, 6)]
    assert all(t["split"] == "test" and t["suite"] == "resilience_closed" for t in tasks)
    assert all(1 <= len(s["ops"]) <= 2 and s["touched"] for s in report["slots"])        # at least one on the plan's elements
    assert tasks[4]["attacks"] and tasks[4]["injected_phrases"] or tasks[4]["attack_targets"]
    manifest = json.loads((base["gen_out"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == gen.CATALOG["seed"] and len(manifest["sha256"]) == 5 + 3           # 5 pages, tasks, report, list


def test_the_draw_is_the_same_every_time_and_covers_every_applicable_operator():
    probes = {f"t{i}": {"ops": {o["id"]: {"applies": True, "touches": o["level"] != 5} for o in gen.CATALOG["operators"]}}
              for i in range(30)}
    a, left = gen.draw(probes, random.Random(gen.CATALOG["seed"]))
    b, _ = gen.draw(probes, random.Random(gen.CATALOG["seed"]))
    assert a == b and left == {"no_page": [], "uncovered": []}
    used = {op for ops in a.values() for op in ops}
    assert used == {o["id"] for o in gen.CATALOG["operators"]}
    assert all(len(ops) == 2 and len(set(ops)) == 2 for ops in a.values())
    touches = lambda op: next(o for o in gen.CATALOG["operators"] if o["id"] == op)["level"] != 5
    assert all(any(touches(op) for op in ops) for (t, lv), ops in a.items() if lv != 5)


def test_an_operator_no_page_allows_is_recorded_and_not_drawn():
    probes = {"t1": {"ops": {o["id"]: {"applies": o["id"] != "L4.popup-deleted", "touches": True} for o in gen.CATALOG["operators"]}}}
    slots, left = gen.draw(probes, random.Random(1))
    assert "L4.popup-deleted" in left["no_page"] and all("L4.popup-deleted" not in ops for ops in slots.values())


def test_a_vetoed_replacement_is_drawn_again_and_after_three_vetoes_another_operator_is_used(base, tmp_path, browser):
    report, _ = run(base, browser)
    listed = list(csv.DictReader((base["gen_out"] / "level2_replacements.csv").read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    if not listed:
        pytest.skip("the draw gave level 2 no synonym on this made-up page")
    first = listed[0]
    vetoes = tmp_path / "vetoes.csv"
    rows = ["task;level;element;word;replacement"]
    for n in range(3):
        rows.append(f"{first['task']};{first['level']};{first['element']};{first['word']};{first['replacement'] if n == 0 else 'x' + str(n)}")
        vetoes.write_text("\n".join(rows) + "\n", encoding="utf-8")
        report, tasks = run(base, browser, vetoes)
        again = list(csv.DictReader((base["gen_out"] / "level2_replacements.csv").read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        same = [r for r in again if r["element"] == first["element"] and r["word"] == first["word"]]
        if n < 2:
            assert same and same[0]["replacement"] != first["replacement"] and int(same[0]["draw"]) == n + 2
    record = next(s for s in report["synonyms"] if s["word"] == first["word"])
    assert record["vetoes"] == 3 and record["limit"]
    assert all(r["word"] != first["word"] or r["element"] != first["element"] for r in again)
    assert all(s["possible"] for s in report["slots"])


def test_an_element_whose_replacements_run_out_gets_another_operator_not_another_element(base, tmp_path, monkeypatch, browser):
    monkeypatch.setattr(gen, "synonyms", lambda word, pos, lang: ["unica"] if word else [])
    run(base, browser)
    listed = list(csv.DictReader((base["gen_out"] / "level2_replacements.csv").read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    if not listed:
        pytest.skip("the draw gave level 2 no synonym on this made-up page")
    f = listed[0]
    vetoes = tmp_path / "vetoes.csv"
    vetoes.write_text(f"task;level;element;word;replacement\n{f['task']};{f['level']};{f['element']};{f['word']};unica\n", encoding="utf-8")
    report, _ = run(base, browser, vetoes)
    again = (base["gen_out"] / "level2_replacements.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(again) == 1                                               # no synonym elsewhere: another operator instead
    assert "L2.synonym" not in next(s for s in report["slots"] if s["level"] == 2)["ops"]
