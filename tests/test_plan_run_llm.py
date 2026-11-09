"""The model in control on the request sets (plan_run --executor llm): the resilience benchmark's executor,
judged by the same answer keys as ANCHOR's runs. A fake model reads the numbered element list the executor
sends, as the real one would."""
import contextlib
import json
import re
from types import SimpleNamespace

import pytest

import eval.plan_run as pr


class FakeModel:
    """Answers like the model: picks the element whose line has `target`, then says it is done."""
    def __init__(self, action=None, target=None, value=None):
        self.action, self.target, self.value, self.calls = action, target, value, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, temperature, messages):
        self.calls += 1
        user = messages[-1]["content"]
        answer = {"action": "done", "element": None, "value": None}
        number = next((int(m.group(1)) for line in user.splitlines()
                       if (m := re.match(r"\[(\d+)\]", line)) and self.target and self.target in line), None)
        if self.action and number and "- (nada ainda)" in user:
            answer = {"action": self.action, "element": number, "value": self.value}
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=10)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))], usage=usage)


def task(task_id):
    return next(t for t in pr.load_tasks() if t["id"] == task_id)


def run(page, the_task, model):
    """As plan_run does: the evaluation's instrumentation in every tab, then the task (pytest-playwright's page)."""
    page.context.add_init_script(pr.INSTRUMENT)
    return pr.run_task_llm(page, SimpleNamespace(client=model, model="fake"), "fake", the_task)


def test_a_task_done_by_the_model_in_control_is_judged_by_its_answer_key(page):
    r = run(page, task("en-log-02"), FakeModel("select", "Português", "Português"))
    assert r.success and r.clean and not r.premature and r.executor == "llm" and not r.reads
    assert r.llm_calls == 2 and r.steps_ok == 1 and json.loads(r.plan)[0][0] == "select"


def test_saying_done_without_doing_it_is_a_false_success(page):
    r = run(page, task("en-log-02"), FakeModel())
    assert not r.success and r.premature and r.checks_ok == 0


def test_a_task_with_expected_readings_is_marked_and_cannot_succeed(page):
    reading = next(t for t in pr.load_tasks() if t.get("extraction") and t.get("split", "dev") == "dev")
    r = run(page, reading, FakeModel())
    assert r.reads and not r.success
    assert pr.expects_readings(reading) and not pr.expects_readings(task("en-log-02"))


@pytest.mark.parametrize("extra", [["--agent"], ["--reference"], ["--no-page"], ["--vision"], []])
def test_the_model_in_control_takes_only_profiles(monkeypatch, extra):
    args = ["--executor", "llm"] + (extra + ["--profiles", "ollama-small"] if extra else [])
    monkeypatch.setattr("sys.argv", ["plan_run"] + args)
    with pytest.raises(SystemExit):
        pr.main()


def test_the_command_reports_the_tasks_with_readings_apart_and_names_its_file(playwright, tmp_path, monkeypatch, capsys):
    """The whole command, with the fake model standing in for Ollama: the table leaves the task with
    expected readings out, reports it apart, and the results file ends in _llm and says its executor."""
    reading = next(t for t in pr.load_tasks() if t.get("extraction") and t.get("split", "dev") == "dev")
    tasks = [task("en-log-02"), {**reading, "suite": "main"}]
    model = FakeModel("select", "Português", "Português")
    monkeypatch.setattr(pr, "load_tasks", lambda: tasks)
    monkeypatch.setattr(pr, "get_profile", lambda name: SimpleNamespace(planner=lambda **kw: SimpleNamespace(client=model, model="fake")))
    monkeypatch.setattr(pr, "warm_up", lambda planner: 0.0)
    monkeypatch.setattr(pr, "environment", lambda planner: {})
    monkeypatch.setattr(pr, "ROOT", tmp_path)
    monkeypatch.setattr(pr, "sync_playwright", lambda: contextlib.nullcontext(playwright))   # pytest-playwright's
    monkeypatch.setattr("sys.argv", ["plan_run", "--executor", "llm", "--profiles", "fake"])
    assert pr.main() == 0
    out = capsys.readouterr().out
    assert "without the 1 run(s) of tasks with expected readings" in out and "The tasks with expected readings, apart:" in out
    saved = list((tmp_path / "results").glob("plans_*_llm.json"))
    assert len(saved) == 1
    data = json.loads(saved[0].read_text(encoding="utf-8"))
    assert data["executor"] == "llm" and data["mode"] == "llm"
    # one task per language here, so the table is per language, as for ANCHOR
    assert data["summary"]["fake [en]"]["tasks"] == 1 and data["summary"]["fake [pt] readings"]["tasks"] == 1
    assert "fake [pt]" not in data["summary"]          # the task with readings is not in the main table
    rows = (tmp_path / "results" / saved[0].name.replace(".json", ".csv")).read_text(encoding="utf-8")
    assert "executor" in rows.splitlines()[0] and "reads" in rows.splitlines()[0]
