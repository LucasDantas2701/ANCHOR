"""The annotation recorder, driven like a person would on a made-up page (never a closed task)."""
import json
from pathlib import Path

from eval.annotate import NOTHING_SENT, RECORDER, build
from eval.plan_run import INSTRUMENT

PAGE = (Path(__file__).parent / "resilience_closed" / "page.html").resolve().as_uri()


def recorded(browser, act):
    ctx = browser.new_context()
    ctx.add_init_script(INSTRUMENT)
    ctx.add_init_script("window.__annot_task = " + json.dumps({"id": "x-1", "request": "salva o cadastro da Ana"}) + ";")
    ctx.add_init_script(RECORDER)
    page = ctx.new_page()
    page.goto(PAGE)
    act(page)
    page.wait_for_function("() => window.__annot.state !== 'working'")
    result = page.evaluate("() => ({...window.__annot, steps: JSON.parse(sessionStorage.getItem('__annot_steps') || '[]')})")
    note = build(result["steps"], result["state"], result.get("answer", ""), result.get("reason", ""), result.get("texts"))
    failing = [c for c in note["checks"] if not page.evaluate(f"() => Boolean({c})")]
    ctx.close()
    return result, note, failing


def test_doing_the_request_gives_the_plan_the_allowed_elements_and_checks_that_hold(browser):
    def act(page):
        page.locator("#nome").fill("Ana Souza")
        page.locator("#nome").dispatch_event("change")
        page.locator("#setor").select_option(label="RH")
        page.locator("[data-eval~=e3]").check()
        page.locator("[data-eval~=e4]").click()
        page.locator("#done").click()                       # the panel's button
    result, note, failing = recorded(browser, act)
    assert result["state"] == "done" and not failing
    assert [s[0] for s in note["reference"]] == ["fill", "select", "check", "click"]
    assert note["reference"][0][2] == "Ana Souza" and note["reference"][1][2] == "RH"
    assert note["allowed"][:2] == ["#nome", "#setor"] and len(note["allowed"]) == 4
    assert any("__clicked" in c for c in note["checks"])


def test_a_question_keeps_the_selected_answer(browser):
    def act(page):
        page.evaluate("""() => { const n = document.querySelector('label[for=nome]').firstChild;
                                  const r = document.createRange(); r.selectNodeContents(n);
                                  getSelection().removeAllRanges(); getSelection().addRange(r); }""")
        page.locator("#answer").click()
    result, note, failing = recorded(browser, act)
    assert result["state"] == "answer" and note["extraction"] == [{"kind": "text", "contains": "Nome completo"}]
    assert note["reference"][-1][0] == "extract_text" and note["checks"] == [NOTHING_SENT] and not failing


def test_an_impossible_request_needs_a_reason_and_sends_nothing(browser):
    def act(page):
        page.locator("#no").click()                         # no reason yet: refused, a message is shown
        assert page.evaluate("() => window.__annot.state") == "working"
        page.locator("#why").fill("a página não tem como excluir")
        page.locator("#no").click()
    result, note, failing = recorded(browser, act)
    assert note["expected"] == "not_possible" and note["why_not_possible"] == "a página não tem como excluir"
    assert note["reference"] == [] and note["allowed"] == [] and note["checks"] == [NOTHING_SENT] and not failing


def test_a_box_ticked_then_unticked_leaves_no_step_and_a_field_keeps_its_last_value():
    steps = [{"action": "fill", "selector": "#a", "label": "campo A", "value": "1"},
             {"action": "check", "selector": "#b", "label": "caixa B", "value": None}]
    note = build(steps, "done")
    assert note["checks"] == ['document.querySelector("#a").value === "1"', 'document.querySelector("#b").checked']


def test_an_annotation_made_by_the_recorder_passes_the_tasks_check(browser, monkeypatch):
    import eval.plan_run as plan_run

    def act(page):
        page.locator("#nome").fill("Ana Souza")
        page.locator("#nome").dispatch_event("change")
        page.locator("[data-eval~=e3]").check()
        page.locator("[data-eval~=e4]").click()
        page.locator("#done").click()
    _, note, _ = recorded(browser, act)
    task = {"id": "x-1", "split": "test", "fixture": "page.html", "request": "cadastra a Ana Souza, aceita os termos e salva", **note}
    monkeypatch.setattr(plan_run, "FIXTURES", Path(__file__).parent / "resilience_closed")
    assert plan_run.check_tasks([task], browser) == 0
