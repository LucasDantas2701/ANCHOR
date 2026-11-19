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
    assert json.dumps(ab.EXECUTOR_NAME) and set(ab.ABLATIONS) == {"no_verify", "model_picks", "no_safety"}


DANGER = """<!doctype html><html lang="en"><body>
<label>Name <input id="name"></label><button onclick="this.dataset.done = 1">Delete account</button>
<label>Password <input id="pw" type="password"></label></body></html>"""


def test_no_safety_keeps_the_barriers_off_whatever_sets_them(page):
    executor = ab.make_executor(page, "no_safety", resolver=ElementResolver(page))
    assert isinstance(executor, ab.NoSafetyExecutor)
    executor.guard, executor.refuse_passwords, executor.confirmer = (lambda *a: "changed"), True, object()
    assert executor.guard is None and executor.refuse_passwords is False and executor.confirmer is None
    ab.agent_class("no_safety")(page, None, executor)                      # the agent turns the refusal on...
    assert executor.refuse_passwords is False                              # ...and it stays off
    plain = ab.make_executor(page, None, resolver=ElementResolver(page))
    Agent(page, None, plain)
    assert plain.refuse_passwords is True                                  # ANCHOR as measured: on


def test_no_safety_types_a_password_where_anchor_refuses(page):
    page.set_content(DANGER)
    anchor = ab.make_executor(page, None, resolver=ElementResolver(page))
    anchor.refuse_passwords = True
    assert anchor.fill("Password", "secret").status == "credential"
    assert page.input_value("#pw") == ""
    ablated = ab.make_executor(page, "no_safety", resolver=ElementResolver(page))
    assert ablated.fill("Password", "secret").status == "success"
    assert page.input_value("#pw") == "secret"


def test_no_safety_agent_blocks_no_step_that_anchor_blocks(page):
    from anchor.planner.plan import Step
    page.set_content(DANGER)
    request, step = "Type Maria in the name field", Step("click", "Delete account")
    anchor = Agent(page, None, ab.make_executor(page, None, resolver=ElementResolver(page)))
    ablated = ab.agent_class("no_safety")(page, None, ab.make_executor(page, "no_safety", resolver=ElementResolver(page)))
    assert anchor._unrequested_destructive(request, step) or anchor._unrequested_submit(request, step)
    assert not (ablated._unrequested_destructive(request, step) or ablated._unrequested_submit(request, step)
                or ablated._wrong_file(request, step) or ablated._wrong_field(request, step))
    assert ab.agent_class(None) is Agent and ab.agent_class("no_verify") is Agent


def test_building_swaps_the_runner_agent_only_for_no_safety():
    import anchor.automations.runner as runner
    for ablation in (None, "no_verify", "model_picks"):
        with ab.building(ablation):
            assert runner.Agent is Agent
    with ab.building("no_safety"):
        assert runner.Agent is ab.NoSafetyAgent
    assert runner.Agent is Agent                                           # restored afterwards


def test_no_safety_has_its_own_rows_and_names():
    assert ab.EXECUTOR_NAME["no_safety"] == "anchor_nosafety"
    row = {"executor": "anchor_nosafety", "run": "2", "success": "True", "llm_calls": "0"}
    assert pt.resilience_executor(row) == "anchor_nosafety2" and pt.resilience_success(row)
    assert "anchor_nosafety2" in pt.EXECUTOR_NAMES and pt.SHORT_EXECUTOR["anchor_nosafety"] == "No barriers"


TWINS = """<!doctype html><html lang="en"><body>
<div><p>Report A</p><button id="a" onclick="this.dataset.done = 1">Open</button></div>
<div><p>Report B</p><button id="b" onclick="this.dataset.done = 1">Open</button></div>
<button id="del" onclick="this.dataset.done = 1">Delete account</button></body></html>"""


def oracle(page, allowed):
    return ab.make_executor(page, "oracle", allowed=allowed, resolver=ElementResolver(page))


def test_the_oracle_picks_the_allowed_candidate_when_anchor_asks(page):
    page.set_content(TWINS)
    executor = oracle(page, ["#b"])
    result = executor.click("Open")
    assert result.status == "success" and result.resolved_by == "user" and executor.questions == 1
    assert page.get_attribute("#b", "data-done") == "1" and page.get_attribute("#a", "data-done") is None


def test_the_oracle_says_none_of_these_when_no_candidate_is_allowed(page):
    page.set_content(TWINS)
    executor = oracle(page, ["#elsewhere"])
    result = executor.click("Open")
    assert result.status == "ambiguous" and result.resolved_by == "user_none" and executor.questions == 1
    assert page.get_attribute("#a", "data-done") is None and page.get_attribute("#b", "data-done") is None


def test_the_oracle_never_picks_between_two_allowed_candidates(page):
    page.set_content(TWINS)
    executor = oracle(page, ["#a", "#b"])               # both allowed: the key cannot tell which is this step's
    result = executor.click("Open")
    assert result.status == "ambiguous" and result.resolved_by == "user_none" and executor.questions == 1
    assert page.get_attribute("#a", "data-done") is None and page.get_attribute("#b", "data-done") is None


def test_the_oracle_approves_an_allowed_sensitive_action_and_denies_another(page):
    page.set_content(TWINS)
    yes = oracle(page, ["#del"])
    assert yes.click("Delete account").status == "success" and yes.questions == 1
    page.set_content(TWINS)
    no = oracle(page, ["#a"])
    assert no.click("Delete account").status == "denied" and no.questions == 1
    assert page.get_attribute("#del", "data-done") is None


def test_anchor_without_the_oracle_asks_no_one_and_stops(page):
    page.set_content(TWINS)
    plain = ab.make_executor(page, None, allowed=["#b"], resolver=ElementResolver(page))
    assert type(plain) is ActionExecutor and plain.click("Open").status == "ambiguous"
    assert not hasattr(plain, "questions") and ab.agent_class("oracle") is Agent and ab.agent_options("oracle") == {}


def test_the_oracle_is_its_own_condition(monkeypatch):
    assert ab.EXECUTOR_NAME["oracle"] == "anchor_oracle" and "oracle" in ab.CONDITIONS and "oracle" not in ab.ABLATIONS
    assert pt.SHORT_EXECUTOR["anchor_oracle"] == "Oracle" and "anchor_oracle2" in pt.EXECUTOR_NAMES
    rows = [{"executor": "anchor_oracle", "profile": "ollama-small", "task": f"t{i}", "split": "dev", "origin": "",
             "questions": str(q), "_file": "x"} for i, q in enumerate([0, 2, 1, 0])]
    table = pt.oracle_questions_table(rows, [])
    assert table[1][3:] == [4, 3, 0.75, 0.5, 2, "50.0"]
