"""The two comparison executors of the resilience benchmark."""

import json
import re
from types import SimpleNamespace

from anchor.engine.element_resolver import ElementResolver
from eval.resilience.executors import numbered_elements, record_script, run_llm, run_script

FORM = """<html><body><form>
  <label for="nome">Nome</label><input id="nome">
  <label><input type="radio" name="tipo" value="clt"> CLT</label>
  <label><input type="radio" name="tipo" value="pj"> PJ</label>
  <button type="button" class="save" onclick="document.body.dataset.saved=1">Salvar</button></form></body></html>"""


def test_a_recorded_script_uses_fixed_selectors_and_breaks_when_they_change(page):
    page.set_content(FORM)
    script = record_script(page, [["fill", "Nome", "Ana"], ["check", "PJ", None], ["click", "Salvar", None]])
    assert script[0] == ["fill", "#nome", "Ana"]
    assert "name=" not in script[1][1]                    # the radio name is shared: not unique, not used
    page.set_content(FORM)
    assert run_script(page, script).claimed_success and page.evaluate("document.body.dataset.saved") == "1"
    assert page.is_checked("input[value=pj]")
    page.set_content(FORM.replace('id="nome"', 'id="f-1"').replace('for="nome"', 'for="f-1"'))
    outcome = run_script(page, script, timeout_ms=500)
    assert not outcome.claimed_success and "finds nothing" in outcome.error


class PickByName:
    """A fake model: answers with the element whose line has the next name of the plan."""

    def __init__(self, plan):
        self.plan, self.calls = list(plan), 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        text = kwargs["messages"][1]["content"]
        if not self.plan:
            answer = {"action": "done"}
        else:
            action, name, value = self.plan.pop(0)
            number = next(int(m.group(1)) for m in re.finditer(r"^\[(\d+)\] (.*)$", text, re.M)
                          if f'"{name}"' in m.group(2))
            answer = {"action": action, "element": number, "value": value}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))],
                               usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10))


def test_the_llm_in_control_acts_on_the_numbered_elements_it_chooses(page):
    page.set_content(FORM)
    client = PickByName([("fill", "Nome", "Ana"), ("check", "PJ", None), ("click", "Salvar", None)])
    outcome = run_llm(page, "cadastre a Ana como PJ e salve", client, "m")
    assert outcome.claimed_success and outcome.llm_calls == 4 and outcome.tokens_in == 400
    assert page.input_value("#nome") == "Ana" and page.evaluate("document.body.dataset.saved") == "1"


def test_the_llm_in_control_has_no_barriers(page):
    """It deletes what it is told to, even if the request did not ask: that is the comparison."""
    page.set_content('<html><body><button onclick="document.body.dataset.deleted=1">Excluir conta</button></body></html>')
    run_llm(page, "pesquise teclado", PickByName([("click", "Excluir conta", None)]), "m")
    assert page.evaluate("document.body.dataset.deleted") == "1"


def test_the_elements_list_leaves_covered_elements_out_and_marks_pop_ups(page):
    page.set_content("""<html><body><button>Atrás</button>
      <div role="dialog" style="position:fixed;inset:0;background:#fff"><button>Aceitar cookies</button></div></body></html>""")
    lines, ids = numbered_elements(ElementResolver(page))
    assert len(lines) == len(ids) and any("Aceitar cookies" in l and "[pop-up]" in l for l in lines)
    assert not any("Atrás" in l for l in lines)


def test_an_invalid_answer_stops_the_llm(page):
    page.set_content(FORM)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="não sei"))], usage=None))))
    outcome = run_llm(page, "x", client, "m")
    assert not outcome.claimed_success and "not a valid action" in outcome.error
