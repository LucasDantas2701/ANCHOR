"""Pages that answer late, and the site's own pop-ups (UI Testing Playground "Wait", 17/10)."""
from anchor.agent import Agent
from anchor.engine.action_executor import ActionExecutor
from anchor.planner import Goal, Plan, Step

LATE = """<html><body><p>Wait page</p>
  <button onclick="window.clicks=(window.clicks||0)+1; setTimeout(()=>alert('Alert is shown after 1.5 seconds'),1500)">Wait for alert!</button>
  <button onclick="setTimeout(()=>{if(confirm('Delete everything?'))document.body.innerHTML='<p>deleted</p>'},200)">Danger</button>
  </body></html>"""


class Planner:
    def __init__(self, *plans):
        self.plans, self.histories = list(plans), []

    def plan(self, request, url, page_elements=None, history=None, **kwargs):
        self.histories.append(list(history or []))
        return self.plans.pop(0) if self.plans else Plan(steps=[])


def test_a_late_alert_is_the_clicks_effect_and_the_button_is_clicked_once(page):
    page.set_content(LATE)
    planner = Planner(Plan(steps=[Step("click", "Wait for alert!", goal="g1")], goals=[Goal("g1", "the alert appeared", True)]))
    result = Agent(page, planner, ActionExecutor(page), report=None).run("click Wait for alert! and see the alert")
    assert result.ok and page.evaluate("window.clicks") == 1                # no second click
    assert any("Alert is shown after 1.5 seconds" in h for hist in planner.histories for h in hist)


def test_the_sites_question_is_answered_no(page):
    page.set_content(LATE)
    planner = Planner(Plan(steps=[Step("click", "Danger", goal="g1")], goals=[Goal("g1", "clicked", True)]))
    Agent(page, planner, ActionExecutor(page), report=None).run("click Danger")
    assert "deleted" not in page.locator("body").inner_text()
    assert any("Delete everything?" in h and "cancel" in h for hist in planner.histories for h in hist)
