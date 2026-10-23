"""The human draw, on made-up exports in the Forms format (never the real one)."""
import csv
import json

import eval.human_sample as hs

HEADER = (["Carimbo de data/hora", "Você concorda em participar? (os pedidos poderão ser publicados)", "Você trabalha com TI?"]
          + [h for i in range(1, 10) for h in (f"P0{i} — o que você pediria nesta página?", f"P0{i} — Você abriu o link?")])


def export(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def person(n, it, consent="Concordo", pages=range(1, 10), opened="Sim"):
    answers = []
    for i in range(1, 10):
        answers += ([f"pedido {n} na página {i}", opened] if i in pages else ["", ""])
    return [f"22/10/2026 10:{n:02d}", consent, "Sim" if it else "Não"] + answers


def test_the_draw_takes_30_and_30_spread_over_the_pages_and_is_the_same_every_time(tmp_path):
    export(tmp_path / "f.csv", [person(n, it=n % 2 == 0) for n in range(40)])
    rows = hs.read_export(tmp_path / "f.csv")
    pool, left_out = hs.candidates(rows, hs.columns(list(rows[0])))
    chosen, record = hs.draw(pool)
    again, _ = hs.draw(pool)
    assert [c["row"] for c in chosen] == [c["row"] for c in again]          # the seed fixes the draw
    assert len(chosen) == 60 and sum(c["profile"] == "it" for c in chosen) == 30 and not record["completions"]
    assert sorted(record["quota"].values()).count(4) == 6                   # 3 per page, 3 extra per profile
    assert all(c["opened_link"] is True for c in chosen) and left_out == {"did_not_agree": 0, "no_profile": 0}


def test_who_did_not_agree_is_left_out_and_short_strata_are_completed_and_recorded(tmp_path):
    rows = [person(n, it=True, pages=[1, 2, 3, 4, 6, 7, 8, 9]) for n in range(20)]         # nobody in IT on P05
    rows += [person(100 + n, it=False) for n in range(20)]
    rows += [person(200, it=True, consent="Não concordo"), person(201, it=True)[:2] + [""] + person(201, it=True)[3:]]
    export(tmp_path / "f.csv", rows)
    data = hs.read_export(tmp_path / "f.csv")
    pool, left_out = hs.candidates(data, hs.columns(list(data[0])))
    chosen, record = hs.draw(pool)
    assert left_out == {"did_not_agree": 1, "no_profile": 1}
    assert not any("200" in c["request"] or "201" in c["request"] for c in chosen)
    filled = [x for x in record["completions"] if x["stratum"] == "it/P05"]
    assert filled and filled[0]["how"] == "other_profile_same_page" and filled[0]["from"] == "non_it/P05"
    assert len(chosen) == 60


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
    assert report["script_commit"] == "abc123" and report["seed"] == hs.SEED and len(report["input_sha256"]) == 64
    assert hs.main([str(tmp_path / "f.csv")]) == 1                          # once: never written over


def test_the_command_refuses_to_run_unless_it_is_exactly_the_committed_file(tmp_path, monkeypatch):
    export(tmp_path / "f.csv", [person(1, it=True)])
    monkeypatch.setattr(hs, "_committed", lambda: "")
    monkeypatch.setattr(hs, "TASKS_OUT", tmp_path / "tasks.json")
    assert hs.main([str(tmp_path / "f.csv")]) == 1 and not (tmp_path / "tasks.json").exists()
