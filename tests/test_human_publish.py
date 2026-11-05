"""The human collection's publication, on made-up exports with the form's titles (never the real one)."""
import csv
import json

import pytest

import eval.human_publish as hp
import eval.human_sample as hs

from .test_human_sample import export, person


def drawn(tmp_path, monkeypatch, rows):
    export(tmp_path / "f.csv", rows)
    monkeypatch.setattr(hs, "TASKS_OUT", tmp_path / "tasks.json")
    monkeypatch.setattr(hs, "REPORT_OUT", tmp_path / "sample.json")
    monkeypatch.setattr(hs, "_committed", lambda: "abc123")
    assert hs.main([str(tmp_path / "f.csv")]) == 0
    return json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))["tasks"]


def published(tmp_path):
    with open(tmp_path / "out" / "responses.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def test_the_responses_are_numbered_before_anything_is_left_out_and_keep_the_drawn_tasks(tmp_path, monkeypatch):
    rows = [person(n, it=n % 2 == 0) for n in range(40)]
    rows.insert(3, person(99, it=True, consent="Não concordo"))          # the 4th response
    tasks = drawn(tmp_path, monkeypatch, rows)
    done = hp.publish(tmp_path / "f.csv", tasks_path=tmp_path / "tasks.json", out=tmp_path / "out")
    table = published(tmp_path)
    numbers = [int(r["response"]) for r in table]
    assert done["published"] == 40 and 4 not in numbers and numbers[:4] == [1, 2, 3, 5]
    assert "Carimbo de data/hora" not in table[0] and "Você trabalha com programação ou TI?" in table[0]
    marked = {t for r in table for t in r["drawn"].split()}
    assert marked == {t["id"] for t in tasks}                           # each of the 60 is on its response's row


def test_a_removal_is_made_in_the_publication_and_in_the_drawn_task_and_logged_without_the_text(tmp_path, monkeypatch):
    tasks = drawn(tmp_path, monkeypatch, [person(n, it=n % 2 == 0) for n in range(40)])
    t = tasks[0]
    n = t["response_row"] - 1
    code = next(c for c, p in hs.PAGES.items() if t["fixture"] == f"collection/{p}")
    field = f"{code} · Pedido" if code in ("P05", "P06", "P07", "P08") else f"{code} · Pedido {t['field']}"
    secret = t["request"].split()[1]                                    # a word of the drawn request
    (tmp_path / "removals.csv").write_text(f"response;field;text;type\n{n};{field};{secret};nome\n", encoding="utf-8")
    done = hp.publish(tmp_path / "f.csv", tmp_path / "removals.csv", tmp_path / "tasks.json", tmp_path / "out")
    row = next(r for r in published(tmp_path) if int(r["response"]) == n)
    task = next(x for x in json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))["tasks"] if x["id"] == t["id"])
    assert "[removido: nome]" in row[field] and secret not in row[field]
    assert "[removido: nome]" in task["request"] and task["removals"] == ["nome"] and done["tasks_affected"] == 1
    log = (tmp_path / "out" / "removals.csv").read_text(encoding="utf-8-sig")
    assert t["id"] in log and "nome" in log and secret not in log      # the log never holds the text


def test_a_removal_whose_text_is_not_there_stops_everything(tmp_path, monkeypatch):
    drawn(tmp_path, monkeypatch, [person(n, it=n % 2 == 0) for n in range(40)])
    (tmp_path / "removals.csv").write_text("response;field;text;type\n1;P01 · Pedido 1;não existe;nome\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        hp.publish(tmp_path / "f.csv", tmp_path / "removals.csv", tmp_path / "tasks.json", tmp_path / "out")
    assert "não existe" not in str(stop.value)                          # the message never repeats the text
