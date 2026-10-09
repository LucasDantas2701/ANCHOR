"""Plan errors are written for the model, and shown to the user in the interface language."""


def test_plan_errors_reach_the_user_in_the_interface_language(monkeypatch):
    from anchor.planner.plan import PlanError
    monkeypatch.setenv("ANCHOR_LANG", "en")
    error = PlanError.of("plan.needs_value", "pt", i=2, action="fill")
    assert str(error) == 'passo 2: a ação "fill" precisa de um valor'              # for the model
    assert error.user_text() == 'step 2: the "fill" action needs a value'           # for the user


def test_the_agent_shows_a_failed_replan_in_the_interface_language(page, monkeypatch):
    from anchor.agent import Agent
    from anchor.engine.action_executor import ActionExecutor
    from anchor.planner import Plan, PlanError, Step
    monkeypatch.setenv("ANCHOR_LANG", "en")

    class Planner:
        calls = 0

        def plan(self, *a, **k):
            Planner.calls += 1
            if Planner.calls == 1:
                return Plan(steps=[Step("click", "Entrar", None)])
            raise PlanError.of("plan.no_conclusive", "pt")

    page.set_content("""<button onclick="document.body.innerHTML='<p>ok</p>'">Entrar</button>""")
    result = Agent(page, Planner(), ActionExecutor(page), report=None).run("entre")
    assert not result.ok and "conclusiva" not in result.message and "conclusive" in result.message
