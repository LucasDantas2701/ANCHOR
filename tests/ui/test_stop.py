"""Stopping a run, even while the AI is replanning inside the agent's catch-alls; and AI sites' notices."""
import time

from anchor.agent.effects import Effect
from anchor.ui.execute import StepwisePlanner
from anchor.ui.runs import Job, RunManager, RunStopped


def test_an_ai_sites_standing_notice_is_not_an_error_message():
    effect = Effect(changed=True, new_messages=["ChatGPT é uma IA e pode cometer erros. Considere verificar informações importantes.",
                                                "Claude can make mistakes. Please double-check responses.",
                                                "CPF inválido", "2 erros no formulário", "Não foi possível salvar o cadastro"])
    assert effect.errors == ["CPF inválido", "2 erros no formulário", "Não foi possível salvar o cadastro"]


def test_a_stop_goes_through_the_agents_catch_alls():
    try:
        try:
            raise RunStopped()
        except Exception:                      # how the agent guards its details
            raise AssertionError("a stop must not be taken for a failure")
    except RunStopped:
        pass


def test_stop_counts_while_the_ai_is_still_writing_a_long_replan():
    class SlowPlanner:                          # a replan that streams for a long time
        language = "en"

        def __init__(self, progress):
            self.progress = progress

        def plan(self, *args, **kwargs):
            for tokens in range(1, 10000):
                try:
                    self.progress("writing", tokens)
                except Exception:              # a catch-all on the way must not swallow the stop
                    pass
                time.sleep(0.01)
            return None

    def runner(job):
        StepwisePlanner(job, lambda progress: SlowPlanner(progress)).plan("request", "url", [], [])
        return {"state": "checked", "message": "done"}

    runs = RunManager(runner)
    job = runs.submit("request", "x", {})
    time.sleep(0.3)
    started = time.time()
    runs.stop(job)
    while job.state == "running" and time.time() - started < 5:
        time.sleep(0.05)
    assert job.state == "stopped" and time.time() - started < 2
