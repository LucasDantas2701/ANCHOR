"""The closed resilience set's final run: its tasks, its integrity check, the reaches-plan mark and the
report's split. No executor runs here on a closed page."""
import hashlib
import json

import eval.resilience.report as report
import eval.resilience.run as run


def test_the_mark_says_base_yes_or_no_from_the_frozen_tasks():
    assert run.reaches_plan({"level": 0}) == "base"
    assert run.reaches_plan({"suite": "resilience_closed", "level": 2, "operators": [{"touched": False}, {"touched": True}]}) == "yes"
    assert run.reaches_plan({"suite": "resilience_closed", "level": 4, "operators": [{"op": "L4.reload-gone", "touched": False}]}) == "no"
    assert run.reaches_plan({"suite": "resilience_closed", "level": 5, "operators": [{"op": "L5.inject-hidden", "touched": False}]}) == "yes"
    assert run.reaches_plan({"level": 3}) == ""                                    # development


def test_the_final_run_has_level_0_and_the_closed_set_split_120_and_30():
    tasks = run.final_tasks()
    marks = [run.reaches_plan(t) for t in tasks]
    assert len(tasks) == 180 and marks.count("base") == 30 and marks.count("yes") == 120 and marks.count("no") == 30
    assert all(run.reaches_plan(t) == "yes" for t in tasks if t["level"] == 5)


def test_the_closed_set_is_still_byte_for_byte_what_its_manifest_recorded():
    assert run.closed_changed() == []


def test_a_changed_file_of_the_closed_set_is_found(tmp_path):
    (tmp_path / "a.html").write_bytes(b"one")
    (tmp_path / "b.html").write_bytes(b"two")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sha256": {"a.html": hashlib.sha256(b"one").hexdigest(),
                                               "b.html": hashlib.sha256(b"other").hexdigest(),
                                               "c.html": "0" * 64}}), encoding="utf-8")
    assert run.closed_changed(manifest, tmp_path) == ["b.html", "c.html"]


def test_the_final_run_refuses_a_changed_working_copy(monkeypatch, capsys):
    monkeypatch.setattr(run, "provenance", lambda: {"commit": "abc1234", "commit_full": "abc1234" * 5, "tag": "v1.0.0",
                                                     "clean": False, "changed": ["anchor/x.py"]})
    assert run.main(["--final", "--executors", "script"]) == 1
    assert "nothing changed" in capsys.readouterr().out


def test_the_report_puts_the_off_path_combinations_apart(tmp_path, capsys):
    def row(level, mark, ok):
        return {"executor": "script", "profile": "", "task": f"t@C{level}", "base_task": "t", "level": level, "language": "pt",
                "run": 1, "success": ok, "claimed_success": ok, "false_success": False, "unrequested": 0, "attacked": False,
                "attack_attempts": 0, "llm_calls": 0, "healed": False, "seconds": 1.0, "error": "", "steps": "[]",
                "reaches_plan": mark}
    f = tmp_path / "r.json"
    f.write_text(json.dumps({"rows": [row(0, "base", True), row(1, "yes", True), row(5, "no", False)]}), encoding="utf-8")
    import sys
    sys_argv = sys.argv
    sys.argv = ["report", str(f)]
    try:
        assert report.main() == 0
    finally:
        sys.argv = sys_argv
    out = capsys.readouterr().out
    assert "Main analysis" in out and "off the task's path" in out
