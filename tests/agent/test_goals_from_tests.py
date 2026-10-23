"""Goals from Lucas's runs (17/10): a goal is met by its last planned step, never by a login page."""
from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Goal, Plan, Step

SEARCH = """<html><body><button onclick="document.getElementById('box').hidden=false">Search</button>
  <div id="box" role="dialog" aria-label="Search" hidden><input aria-label="Search field">
  <button onclick="document.body.insertAdjacentHTML('beforeend','<p>12 results</p>')">Go</button></div></body></html>"""
REPO = """<html><body><h1>ollama/ollama</h1><a href="#" onclick="document.body.innerHTML='<h1>Sign in</h1><input type=password>';return false">Star</a></body></html>"""


class Planner:
    def __init__(self, *plans):
        self.plans, self.histories = list(plans), []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.histories.append(list(history or []))
        return self.plans.pop(0) if self.plans else Plan(steps=[])


def goals_line(histories):
    return [h for hist in histories for h in hist if h.startswith(("metas:", "goals:"))]


def test_a_goal_with_several_steps_is_not_met_by_its_first_one(page):
    page.set_content(SEARCH)
    goal = [Goal("g1", "busca executada", conclusive=True)]
    first = Plan(steps=[Step("click", "Search", goal="g1"), Step("fill", "Search field", "ollama", goal="g1"),
                        Step("click", "Go", goal="g1")], goals=goal)
    planner = Planner(first)
    Agent(page, planner, ActionExecutor(page), report=None).run("search for ollama")
    # the box appearing after the first click makes the agent plan again: the goal must still be pending then
    assert len(planner.histories) >= 2
    told = goals_line(planner.histories[1:2])
    assert told and ("pendente" in told[0] or "pending" in told[0]), told


def test_a_step_that_leads_to_a_login_page_does_not_meet_its_goal(page):
    page.set_content(REPO)
    planner = Planner(Plan(steps=[Step("click", "Star", goal="g1")], goals=[Goal("g1", "repositório favoritado", True)]))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("favorite o repositorio ollama")
    assert not result.ok and result.goals_done == 0


def test_a_step_that_leads_to_a_login_page_waits_for_the_login_and_plans_again(page):
    page.set_content(REPO)
    starred = '<html><body><h1>ollama/ollama</h1><button onclick="this.textContent=&#39;Starred&#39;">Star</button></body></html>'

    class Waiter:
        calls = 0

        def wait(self, url, signup=False):
            Waiter.calls += 1
            page.set_content(starred)            # the person logged in; GitHub went back to the repository
            return True

    planner = Planner(Plan(steps=[Step("click", "Star", goal="g1")], goals=[Goal("g1", "repositório favoritado", True)]),
                      Plan(steps=[Step("click", "Star", goal="g1")], goals=[Goal("g1", "repositório favoritado", True)]))
    result = Agent(page, planner, ActionExecutor(page), report=None, login=Waiter()).run("favorite o repositorio ollama")
    assert Waiter.calls == 1 and result.ok and page.locator("button").inner_text() == "Starred"
    assert any("levou a uma página de login" in h for h in planner.histories[1])


def test_a_new_plan_that_starts_with_the_step_just_done_goes_on_with_the_next_one(page):
    """LinkedIn, 17/10: after opening a post's "…" menu, the plan repeated it before "Salvar", and failed three times."""
    page.set_content("""<html><body><article><p>Post</p><button aria-haspopup="menu"
      onclick="document.body.insertAdjacentHTML('beforeend','<div role=menu><button onclick=&quot;this.textContent=\\'Salvo\\'&quot;>Salvar</button></div>')">… mais</button>
      </article></body></html>""")
    first = Plan(steps=[Step("click", "… mais", goal="g1")], goals=[Goal("g1", "publicação salva", True)])
    again = Plan(steps=[Step("click", "… mais", goal="g1"), Step("click", "Salvar", goal="g1")], goals=[Goal("g1", "publicação salva", True)])
    planner = Planner(first, again)
    result = Agent(page, planner, ActionExecutor(page), report=None).run("salve a publicação")
    assert result.ok and page.get_by_role("button", name="Salvo").count() == 1
    assert any("não repetido" in h for hist in planner.histories for h in hist)


def test_steps_on_a_login_page_still_meet_their_goals(page):
    """The dev suite's login tasks (21/10): on a login page every step has a password field beside it."""
    page.set_content('<h1>Entrar</h1><label>Usuário <input id="u"></label><label>Senha <input type="password"></label>'
                     '<label><input type="checkbox" id="r"> Lembrar de mim</label><button>Entrar</button>')
    planner = Planner(Plan(steps=[Step("fill", "Usuário", "maria", goal="g1"), Step("check", "Lembrar de mim", goal="g2")],
                           goals=[Goal("g1", "usuário preenchido", True), Goal("g2", "lembrar marcado", True)]))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("preencha o usuário maria e marque lembrar de mim")
    assert result.ok and result.goals_done == 2, result.message


def test_a_search_opened_but_not_sent_is_not_done(page):
    """en-pop-01 (21/10): after the pop-up, the plan typed the coin and the model said nothing was left."""
    import pathlib
    page.goto((pathlib.Path(__file__).parents[2] / "eval" / "fixtures" / "search_popup.html").as_uri())
    goal = [Goal("g1", "the coin was searched", True)]
    planner = Planner(Plan(steps=[Step("click", "Search /", goal="g1"), Step("fill", "Search coins", "Pi Network", goal="g1"),
                                  Step("press", "Search coins", "Enter", goal="g1")], goals=goal),
                      Plan(steps=[Step("click", "Search /", goal="g1"), Step("fill", "Search coins", "Pi Network", goal="g1")], goals=goal))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("Search for the Pi Network coin")
    assert not result.ok, result.message                     # never "done" without the Enter


def test_a_goal_is_met_even_if_a_later_step_only_repeats_the_one_that_met_it(page):
    """en-u-app-03 (21/10): the 4B model attached resume.pdf, then planned the same upload under a
    label in Portuguese; that repeat failed, and the goal stayed pending with the resume attached."""
    import pathlib
    root = pathlib.Path(__file__).parents[2]
    page.goto((root / "eval" / "fixtures" / "application_en.html").as_uri())
    f = "eval/fixtures/files/"
    planner = Planner(Plan(steps=[Step("upload", "Attach resume", f + "resume.pdf", goal="g1"),
                                  Step("upload", "Anexar currículo", f + "resume.pdf", goal="g1"),
                                  Step("upload", "Profile photo", f + "photo.png", goal="g2")],
                           goals=[Goal("g1", "anexar currículo"), Goal("g2", "anexar foto")]))
    result = Agent(page, planner, ActionExecutor(page), report=None, output_dir=str(root)).run(
        "attach the resume eval/fixtures/files/resume.pdf and the photo eval/fixtures/files/photo.png")
    assert result.ok and result.goals_done == 2, result.message
