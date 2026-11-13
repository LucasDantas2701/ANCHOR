"""The two ablations of ANCHOR (eval/ablations.py, decided on 13/11/2026): with none chosen, the runners build
ANCHOR exactly as measured; each ablation removes only its part."""
import json
from types import SimpleNamespace

import pytest

import eval.ablations as ab
import eval.paper_tables as pt
import eval.plan_run as pr
from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver

PAGE = """<!doctype html><html lang="en"><body>
<button onclick="this.dataset.done = 1">Save</button><button onclick="this.dataset.done = 1">Cancel</button>
<p id="total">Total: 182,400</p></body></html>"""


class Picker:
    """A model that answers with a fixed element number, and counts its calls."""
    def __init__(self, answer):
        self.answer, self.seen = answer, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=2)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))], usage=usage)


def test_with_no_ablation_the_runners_build_anchor_as_measured(page):
    executor = ab.make_executor(page, None, resolver=ElementResolver(page))
    assert type(executor) is ActionExecutor and ab.agent_options(None) == {} and ab.EXECUTOR_NAME[None] == "anchor"
    assert Agent(page, None, executor).watcher is not None                     # the effect check is on


def test_no_verify_turns_off_only_the_effect_check(page):
    executor = ab.make_executor(page, "no_verify", resolver=ElementResolver(page))
    assert type(executor) is ActionExecutor
    assert Agent(page, None, executor, **ab.agent_options("no_verify")).watcher is None


def test_model_picks_lets_the_model_choose_the_element_from_the_numbered_list(page):
    page.set_content(PAGE)
    model = Picker("2")                                       # the second element of the list: Cancel
    executor = ab.make_executor(page, "model_picks", SimpleNamespace(client=model, model="fake"), resolver=ElementResolver(page))
    result = executor.click("Save button")
    assert result.status == "success" and page.locator("text=Cancel").get_attribute("data-done") == "1"
    assert executor.calls == 1 and model.seen[0]["seed"] == 7 and model.seen[0]["temperature"] == 0
    assert '"Save button"' in model.seen[0]["messages"][-1]["content"] and "[2]" in model.seen[0]["messages"][-1]["content"]


def test_model_picks_refuses_when_the_model_picks_nothing_and_reads_with_the_resolver(page):
    page.set_content(PAGE)
    model = Picker("0")
    executor = ab.make_executor(page, "model_picks", SimpleNamespace(client=model, model="fake"), resolver=ElementResolver(page))
    assert executor.click("Save button").status == "not_found"
    read = executor.extract_text("the total")
    assert read.status == "success" and "182,400" in read.value and executor.calls == 1      # no pick for a reading


def test_an_ablation_needs_the_agent(monkeypatch):
    monkeypatch.setattr("sys.argv", ["plan_run", "--ablation", "no_verify", "--profiles", "ollama-small"])
    with pytest.raises(SystemExit):
        pr.main()


def test_the_tables_treat_each_ablation_as_a_system_with_two_runs():
    row = {"executor": "anchor_noverify", "run": "2", "success": "True", "llm_calls": "0"}
    assert pt.resilience_executor(row) == "anchor_noverify2" and pt.resilience_success(row)
    assert not pt.resilience_success({**row, "executor": "anchor_modelpick", "llm_calls": "3"})
    assert pt.EXECUTOR_NAMES["anchor_modelpick1"].startswith("ANCHOR, element chosen by the model")
    assert json.dumps(ab.EXECUTOR_NAME) and set(ab.ABLATIONS) == {"no_verify", "model_picks"}
