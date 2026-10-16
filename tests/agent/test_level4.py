"""Level 4 of the resilience benchmark, on its real pages: a field behind "Mostrar mais" under a cookie banner."""

from pathlib import Path

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step

L4 = Path(__file__).resolve().parents[2] / "eval" / "fixtures" / "resilience" / "L4"


class Plans:
    def __init__(self, *plans):
        self.plans, self.histories = [list(p) for p in plans], []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.histories.append(list(history or []))
        return Plan(steps=[Step(*s) for s in (self.plans.pop(0) if self.plans else [])])


def test_a_hidden_field_under_a_cookie_banner_is_reached(page):
    page.goto((L4 / "login.html").as_uri())
    planner = Plans([("fill", "Username", "lucas.dantas"), ("check", "Remember me", None)])
    result = Agent(page, planner, ActionExecutor(page), report=None).run(
        "Preencha o usuário lucas.dantas e marque para lembrar de mim")
    assert result.ok, result.message
    assert page.evaluate("[...document.querySelectorAll('input[type=checkbox]')].some(c => c.checked)")


BANNER = """<div role="dialog" aria-modal="true" style="position:fixed;inset:0;background:#fff;z-index:99">
  <p>{text}</p>{buttons}</div>
<button onclick="document.body.dataset.saved = 1">Salvar</button>"""


def run(page, planner, request):
    return Agent(page, planner, ActionExecutor(page), report=None).run(request)


def test_a_cookie_banner_in_the_way_is_declined_never_accepted(page):
    page.set_content(BANNER.format(text="Usamos cookies.", buttons=
        '<button onclick="document.body.dataset.accepted = 1; this.parentElement.remove()">Aceitar cookies</button>'
        '<button onclick="document.body.dataset.declined = 1; this.parentElement.remove()">Recusar</button>'))
    result = run(page, Plans([("click", "Salvar", None)]), "salve")
    assert result.ok, result.message
    assert page.evaluate("[document.body.dataset.saved, document.body.dataset.declined, document.body.dataset.accepted]") == ["1", "1", None]


def test_a_banner_with_no_way_to_decline_is_left_alone(page):
    page.set_content(BANNER.format(text="Usamos cookies.", buttons=
        '<button onclick="document.body.dataset.accepted = 1; this.parentElement.remove()">Aceitar cookies</button>'))
    run(page, Plans([("click", "Salvar", None)]), "salve")
    assert page.evaluate("document.body.dataset.accepted") is None


def test_another_layer_over_show_more_is_not_closed_and_the_planner_is_told(page):
    page.set_content("""<label>Nome <input></label>
        <button onclick="this.nextElementSibling.hidden = false; this.remove()">Mostrar mais</button>
        <div hidden><label>Telefone <input id="phone"></label></div>
        <div role="dialog" aria-modal="true" style="position:fixed;inset:0;background:#fff;z-index:99">
          <p>Promoção de hoje!</p><button onclick="this.parentElement.remove()">Fechar</button></div>""")
    planner = Plans([("fill", "Telefone", "92 99999-0000")])
    run(page, planner, "preencha o telefone 92 99999-0000")
    assert page.evaluate("!!document.querySelector('[role=dialog]')")          # left for the planner to decide
    assert any('atrás de "Mostrar mais"' in " ".join(h) for h in planner.histories)


def test_a_banner_over_the_target_is_declined_before_trying_the_click(page):
    """Seen on Windows: the click waited 30 s for the covered button before the banner was declined."""
    import time
    page.goto((Path(__file__).parent / "cookie_banner_page.html").as_uri())     # the page of that run
    start = time.monotonic()
    result = run(page, Plans([("fill", "Nome", "Maria Silva"), ("click", "Salvar cadastro", None)]),
                 "preencha o nome Maria Silva e salve o cadastro")
    assert result.ok and not page.evaluate("!!document.getElementById('cookies')"), result.message
    assert "salvo" in page.inner_text("#ok")
    assert time.monotonic() - start < 10
