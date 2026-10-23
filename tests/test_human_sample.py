"""The human draw, on made-up exports with the form's exact titles (criar_formulario.gs), never the real one."""
import csv
import json

import eval.human_sample as hs

TWO = {"P01", "P02", "P03", "P04", "P09"}                  # the pages with two request fields
FIELDS = {c: (["Pedido 1", "Pedido 2"] if c in TWO else ["Pedido"]) for c in sorted(hs.PAGES)}
HEADER = (["Carimbo de data/hora", "Você concorda em participar nessas condições?", "Você trabalha com programação ou TI?"]
          + [t for c, f in FIELDS.items() for t in [f"{c} · Você abriu o link desta página?"] + [f"{c} · {x}" for x in f]])


def export(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def person(n, it, consent="Li e concordo", at=None, opened="Sim"):
    answers = []
    for c, f in FIELDS.items():
        answers += [opened] + [f"pedido {n} {c} {x}" for x in f]
    return [at or f"22/10/2026 14:{n % 60:02d}:{n // 60:02d}", consent, "Sim" if it else "Não"] + answers


def pool_of(tmp_path, rows):
    export(tmp_path / "f.csv", rows)
    data = hs.read_export(tmp_path / "f.csv")
    return hs.candidates(data, hs.columns(list(data[0])))


def test_the_forms_titles_are_recognised_with_both_request_fields():
    cols = hs.columns(HEADER)
    assert cols["time"] and cols["consent"] and cols["profile"] and set(cols["opened"]) == set(hs.PAGES)
    assert {c: len(f) for c, f in cols["requests"].items()} == {c: len(f) for c, f in FIELDS.items()}


def test_a_response_gives_its_14_requests_and_the_pilot_and_who_did_not_agree_are_left_out(tmp_path):
    pool, left_out = pool_of(tmp_path, [person(1, True), person(2, False, consent="Não concordo"),
                                         person(3, True, at="22/10/2026 13:18:01"), person(4, True, at="2026/10/22 1:18:01 PM GMT-4")])
    assert left_out == {"pilot": 2, "did_not_agree": 1, "no_profile": 0}
    assert len(pool) == 14 and {c["position"] for c in pool if c["code"] == "P01"} == {1, 2}


def test_the_draw_takes_30_and_30_one_request_per_person_first_and_is_the_same_every_time(tmp_path):
    pool, _ = pool_of(tmp_path, [person(n, it=n % 2 == 0) for n in range(40)])
    chosen, record = hs.draw(pool)
    again, _ = hs.draw(pool)
    assert [(c["row"], c["position"]) for c in chosen] == [(c["row"], c["position"]) for c in again]
    assert len(chosen) == 60 and sum(c["profile"] == "it" for c in chosen) == 30 and not record["completions"]
    strata = {}
    for c in chosen:
        strata.setdefault(c["stratum"], []).append(c["row"])
    assert all(len(rows) == len(set(rows)) for rows in strata.values())      # 20 people each: never one twice


def test_a_short_stratum_is_completed_and_recorded(tmp_path):
    rows = [person(n, it=True) for n in range(20)] + [person(100 + n, it=False) for n in range(20)]
    for r in rows[:20]:                                   # nobody in IT wrote on P05
        r[HEADER.index("P05 · Pedido")] = ""
    pool, _ = pool_of(tmp_path, rows)
    chosen, record = hs.draw(pool)
    filled = [x for x in record["completions"] if x["stratum"] == "it/P05"]
    assert filled and filled[0]["how"] == "other_profile_same_page" and filled[0]["from"] == "non_it/P05" and len(chosen) == 60


def test_the_times_of_both_export_formats_are_read():
    assert hs.when("22/10/2026 13:18:01") == hs.when("2026/10/22 1:18:01 PM GMT-4") == "2026-10-22 13:18:01"
    assert hs.when("2026/10/22 12:05:00 AM GMT-4") == "2026-10-22 00:05:00" and hs.when("ontem") == ""


def test_the_command_writes_the_tasks_to_annotate_prints_no_request_and_draws_once(tmp_path, monkeypatch, capsys):
    export(tmp_path / "f.csv", [person(n, it=n % 2 == 0) for n in range(40)])
    monkeypatch.setattr(hs, "TASKS_OUT", tmp_path / "tasks.json")
    monkeypatch.setattr(hs, "REPORT_OUT", tmp_path / "sample.json")
    monkeypatch.setattr(hs, "_committed", lambda: "abc123")
    assert hs.main([str(tmp_path / "f.csv")]) == 0
    out = capsys.readouterr().out
    assert "pedido" not in out and "drawn 60" in out
    tasks = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert len(tasks) == 60 and all(t["checks"] == [] and t["origin"] == "human" and t["split"] == "test" for t in tasks)
    assert {t["fixture"] for t in tasks} <= {f"collection/{p}" for p in hs.PAGES.values()}
    report = json.loads((tmp_path / "sample.json").read_text(encoding="utf-8"))
    assert report["script_commit"] == "abc123" and report["seed"] == hs.SEED and report["left_out"]["pilot"] == 0
    assert hs.main([str(tmp_path / "f.csv")]) == 1                          # once: never written over


def test_the_command_refuses_to_run_unless_it_is_exactly_the_committed_file(tmp_path, monkeypatch):
    export(tmp_path / "f.csv", [person(1, it=True)])
    monkeypatch.setattr(hs, "_committed", lambda: "")
    monkeypatch.setattr(hs, "TASKS_OUT", tmp_path / "tasks.json")
    assert hs.main([str(tmp_path / "f.csv")]) == 1 and not (tmp_path / "tasks.json").exists()
