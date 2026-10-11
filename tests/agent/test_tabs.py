"""New tabs: the agent follows the tab a click opened, goes back when it closes, and nothing is left on the old tab."""

from pathlib import Path

from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Plan, Step

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


class Plans:
    """One plan per call (the first plan, then one per replan)."""

    def __init__(self, *plans):
        self.plans, self.histories = [list(p) for p in plans], []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.histories.append(list(history or []))
        steps = self.plans.pop(0) if self.plans else []
        return Plan(steps=[Step(*s) for s in steps])


def run(page, planner, request, **kwargs):
    agent = Agent(page, planner, ActionExecutor(page), report=None, **kwargs)
    return agent, agent.run(request)


def test_a_link_that_opens_a_new_tab_is_followed(page):
    page.goto((FIXTURES / "help.html").as_uri())
    planner = Plans([("click", "Abrir formulário de suporte", None)], [("fill", "Nome", "Ana Souza")])
    agent, result = run(page, planner, "abra o formulário de suporte e preencha o nome Ana Souza")
    assert result.ok, result.message
    assert agent.page is not page and agent.page.url.endswith("support_form.html")
    assert agent.executor.page is agent.page and agent.executor.resolver.page is agent.page
    assert agent.page.input_value("#name") == "Ana Souza"
    assert any("aba nova" in " ".join(h) for h in planner.histories)            # the planner was told


def test_a_window_opened_by_a_button_is_followed_and_read(page):
    page.goto((FIXTURES / "help_en.html").as_uri())
    planner = Plans([("click", "View service policy", None)], [("extract_text", "We answer every message", None)])
    agent, result = run(page, planner, "what is the response time in the service policy?")
    assert result.ok, result.message and "48 business hours" in result.extractions[0]["text"]


def test_a_plain_link_does_not_change_tabs(page):
    page.goto((FIXTURES / "help.html").as_uri())
    agent, result = run(page, Plans([("click", "Perguntas frequentes", None)]), "abra as perguntas frequentes")
    assert agent.page is page and len(page.context.pages) == 1


def test_when_the_tab_closes_the_agent_goes_back(page, tmp_path):
    (tmp_path / "popup.html").write_text('<h1>Pagamento</h1><button onclick="window.close()">Concluir pagamento</button>')
    (tmp_path / "shop.html").write_text(
        '<button onclick="window.open(\'popup.html\')">Pagar</button>'
        '<button onclick="document.body.dataset.done = 1">Ver pedido</button>')
    page.goto((tmp_path / "shop.html").as_uri())
    planner = Plans([("click", "Pagar", None)], [("click", "Concluir pagamento", None)], [("click", "Ver pedido", None)])
    agent, result = run(page, planner, "pague, conclua o pagamento e veja o pedido", verify_effect=False)
    assert agent.page is page and page.evaluate("document.body.dataset.done") == "1", result.message


def test_a_download_in_the_new_tab_is_kept(page, tmp_path):
    page.goto((FIXTURES / "help.html").as_uri())
    (tmp_path / "out").mkdir()
    docs = (FIXTURES / "documents.html").as_uri()
    page.set_content(f'<a href="{docs}" target="_blank">Abrir documentos</a>')
    planner = Plans([("click", "Abrir documentos", None)], [("download", "Baixar contrato", None)])
    agent, result = run(page, planner, "abra os documentos e baixe o contrato", output_dir=tmp_path / "out")
    assert [e["name"] for e in result.extractions] == ["contrato-servico.pdf"], result.message


def test_closing_the_opened_tabs_points_the_executor_back_at_the_first_tab(page):
    page.goto((FIXTURES / "help.html").as_uri())
    planner = Plans([("click", "Abrir formulário de suporte", None)], [("fill", "Nome", "Ana")])
    agent, result = run(page, planner, "abra o formulário de suporte e preencha o nome Ana")
    agent.close_opened_tabs()
    assert len(page.context.pages) == 1 and agent.executor.page is page and agent.executor.resolver.page is page


def test_a_tab_the_page_opened_by_itself_is_not_followed(page, tmp_path):
    """A tab that opens between steps (an ad) is not the step's doing, and is not followed."""
    (tmp_path / "ad.html").write_text("<h1>Oferta imperdível</h1>")
    (tmp_path / "home.html").write_text('<button onclick="document.body.dataset.done = 1">Continuar</button>')
    page.goto((tmp_path / "home.html").as_uri())

    class AdWhilePlanning(Plans):
        def plan(self, *args, **kwargs):
            if not self.histories:                       # the run has started; no step has run yet
                page.evaluate("window.open('ad.html')")
                page.wait_for_timeout(300)
            return super().plan(*args, **kwargs)

    agent, result = run(page, AdWhilePlanning([("click", "Continuar", None)]), "clique em continuar", verify_effect=False)
    assert agent.page is page and page.evaluate("document.body.dataset.done") == "1"


def test_a_question_is_not_done_until_the_answer_is_read():
    """The models opened the policy tab and stopped: a question needs a step that reads the answer."""
    import pytest

    from anchor.planner import PlanError
    from anchor.planner.plan import check_request, is_question
    assert is_question("qual é o prazo de resposta da política?") and is_question("what is the response time")
    assert not is_question("abra o formulário de suporte e preencha o nome Ana")
    with pytest.raises(PlanError, match="pergunta"):
        check_request([Step("click", "Ver política de atendimento")], [], "qual é o prazo de resposta da política?")
    check_request([Step("click", "Ver política de atendimento"), Step("extract_text", "Respondemos em até 48 horas")],
                  [], "qual é o prazo de resposta da política?")


def test_the_agent_reads_the_answer_in_the_new_tab_after_the_warning(page):
    page.goto((FIXTURES / "help.html").as_uri())
    # 1st: open the policy; after the tab and at the end check: "nothing left" (the models' mistake);
    # after the warning: read it.
    planner = Plans([("click", "Ver política de atendimento", None)], [], [],
                    [("extract_text", "Respondemos todas as mensagens", None)])
    agent, result = run(page, planner, "qual é o prazo de resposta da política de atendimento?")
    assert result.ok, result.message
    assert "48 horas" in result.extractions[0]["text"]
    assert any("pergunta" in " ".join(h) for h in planner.histories)          # the planner got the warning
