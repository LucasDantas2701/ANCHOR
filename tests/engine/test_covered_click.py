"""A click on an element under something (LinkedIn, 17/10: "click Vagas" waited 30 s, twice, saying only "Timeout")."""
import time

from anchor.agent.agent import failure_reason
from anchor.engine.action_executor import ActionExecutor


def test_a_covered_click_fails_soon_and_says_what_covers_it(page):
    page.set_content('<nav><a href="#jobs">Vagas</a></nav><div style="position:fixed;inset:0;background:#fff8">'
                     '<p>Mensagens</p></div>')
    executor = ActionExecutor(page)
    executor.click_timeout_ms = 1500
    start = time.time()
    result = executor.click("Vagas")
    assert result.status == "error" and time.time() - start < 6
    reason = failure_reason(result)
    assert reason.key == "why.covered_by" and "Mensagens" in reason.values["what"], (reason.key, reason.values, result.error[-300:])
