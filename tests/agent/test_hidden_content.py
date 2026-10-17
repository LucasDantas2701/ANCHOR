"""Hidden content: a target behind "Show more" or a collapsed section is revealed, not replanned around."""

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step

FORM = """<form onsubmit="return false">
  <label>Nome <input id="name"></label>
  <button type="button" onclick="this.nextElementSibling.hidden = false; this.remove()">{button}</button>
  <div hidden><label>Telefone <input id="phone"></label></div>
</form>"""


class Plans:
    def __init__(self, *plans):
        self.plans, self.calls = [list(p) for p in plans], 0

    def plan(self, *args, **kwargs):
        self.calls += 1
        return Plan(steps=[Step(*s) for s in (self.plans.pop(0) if self.plans else [])])


def run(page, planner, request):
    return Agent(page, planner, ActionExecutor(page), report=None).run(request)


def test_a_field_behind_show_more_is_revealed_and_filled_without_a_replan(page):
    page.set_content(FORM.format(button="Mostrar mais"))
    planner = Plans([("fill", "Nome", "Ana"), ("fill", "Telefone", "92 99999-0000")])
    result = run(page, planner, "preencha o nome Ana e o telefone 92 99999-0000")
    assert result.ok, result.message
    assert page.input_value("#phone") == "92 99999-0000" and planner.calls == 2      # the plan and the end check


def test_a_collapsed_section_counts_too(page):
    page.set_content("""<button aria-expanded="false" onclick="this.setAttribute('aria-expanded','true');
        document.getElementById('more').hidden = false">Endereço</button>
        <div id="more" hidden><label>CEP <input id="cep"></label></div>""")
    result = run(page, Plans([("fill", "CEP", "69000-000")]), "preencha o CEP 69000-000")
    assert result.ok and page.input_value("#cep") == "69000-000", result.message


def test_a_button_with_an_action_verb_is_not_clicked_to_reveal(page):
    page.set_content(FORM.format(button="Mostrar mais e salvar"))
    page.evaluate("document.querySelector('button').addEventListener('click', () => document.body.dataset.saved = 1)")
    run(page, Plans([("fill", "Telefone", "92 99999-0000")]), "preencha o telefone 92 99999-0000")
    assert page.evaluate("document.body.dataset.saved") is None


def test_without_reveal_controls_nothing_changes(page):
    page.set_content("<label>Nome <input id='name'></label><button>Salvar</button>")
    result = run(page, Plans([("fill", "Telefone", "92 99999-0000")]), "preencha o telefone 92 99999-0000")
    assert not result.ok and result.records[0].status == "not_found"
