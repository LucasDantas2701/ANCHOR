"""Saved automations: the first run learns the plan, the next ones replay it without the LLM."""

import pytest

from anchor.automations import Automation, AutomationError, AutomationStore, run_automation
from anchor.engine.action_executor import ActionExecutor
from anchor.engine.memory import ChoiceMemory
from anchor.planner import Goal, Plan, Step

FORM = """<html><body>
  <label for="nome">Nome</label><input id="nome">
  <button onclick="document.getElementById('m').textContent='Cadastro salvo'">{save}</button>
  <p id="m" role="status"></p></body></html>"""


class LearningPlanner:
    """Plays the LLM in the learning run: a ready-made plan, then "nothing is left"."""

    def __init__(self, *plans):
        self.plans, self.calls = list(plans), 0

    def plan(self, request, url, page_elements=None, history=None, **_):
        self.calls += 1
        goals, steps = self.plans.pop(0) if self.plans else ([], [])
        return Plan(steps=[Step(*s) for s in steps], goals=goals)


def no_llm(_automation):
    raise AssertionError("a replay must not call the LLM")


GOALS = [Goal("g1", "nome preenchido"), Goal("g2", "cadastro salvo", True)]
PLAN = [("fill", "Nome", "Maria", "g1", None), ("click", "Salvar", None, "g2", "salvo")]


@pytest.fixture
def store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="register", request="cadastre a Maria e salve", url="about:blank", profile="x"))
    return s


def run(store, page, make_planner, **kw):
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("register")))
    return run_automation(store, "register", page, executor, make_planner, report=None, **kw)


def test_first_run_learns_and_saves_the_plan_that_worked(page, store):
    page.set_content(FORM.format(save="Salvar"))
    planner = LearningPlanner((GOALS, [("click", "Botão que não existe", None, "g1", None)]),
                              ([], PLAN), ([], []))
    result, mode, run_id = run(store, page, lambda _: planner)
    assert result.ok and mode == "learn"
    plan = store.load_plan("register")
    assert [(s.action, s.description) for s in plan.steps] == [("fill", "Nome"), ("click", "Salvar")]
    assert {g.id for g in plan.goals} == {"g1", "g2"} and plan.source_run == run_id
    assert store.runs("register")[0]["mode"] == "learn"


def test_next_runs_replay_without_the_llm(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Salvar"))
    result, mode, _ = run(store, page, no_llm)
    assert result.ok and mode == "replay" and result.llm_calls == 0
    assert page.input_value("#nome") == "Maria" and "Cadastro salvo" in page.inner_text("body")


def test_replay_stops_when_the_site_changed(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.replace('<button onclick="document.getElementById(\'m\').textContent=\'Cadastro salvo\'">{save}</button>', ""))
    result, mode, _ = run(store, page, no_llm)              # the save button is gone
    assert mode == "replay" and result.status == "failed"
    assert result.message.startswith("the saved plan stopped working")
    assert store.runs("register")[-1]["status"] == "failed"


def test_failed_learning_saves_no_plan(page, store):
    page.set_content(FORM.format(save="Salvar"))
    bad = [("click", "Botão que não existe", None, "g1", None)]
    run(store, page, lambda _: LearningPlanner((GOALS, bad), ([], bad), ([], bad)))
    assert store.load_plan("register") is None


def test_relearn_replaces_the_approved_plan(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Gravar dados"))
    new_plan = [("fill", "Nome", "Maria", "g1", None), ("click", "Gravar dados", None, "g2", None)]
    result, mode, _ = run(store, page, lambda _: LearningPlanner((GOALS, new_plan), ([], [])), relearn=True)
    assert result.ok and mode == "learn"
    assert store.load_plan("register").steps[1].description == "Gravar dados"


def test_replay_follows_a_page_change(page, store, tmp_path):
    (tmp_path / "p2.html").write_text('<html><body><label for="c">CPF</label><input id="c">'
                                      '<button onclick="document.body.dataset.ok=1">Enviar</button></body></html>',
                                      encoding="utf-8")
    (tmp_path / "p1.html").write_text('<html><body><label for="n">Nome</label><input id="n">'
                                      '<a href="p2.html">Próximo</a></body></html>', encoding="utf-8")
    steps = [("fill", "Nome", "Maria", "g1", None), ("click", "Próximo", None, "g1", None),
             ("fill", "CPF", "123", "g2", None), ("click", "Enviar", None, "g2", None)]
    goals = [Goal("g1", "nome"), Goal("g2", "enviado", True)]
    store.create(Automation(name="wizard", request="preencha a Maria, o CPF 123 e envie", url="x", profile="x"))

    def run_wizard(make_planner):
        page.set_default_timeout(1500)
        executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("wizard")))
        return run_automation(store, "wizard", page, executor, make_planner, report=None)

    page.goto((tmp_path / "p1.html").as_uri())
    learned, _, _ = run_wizard(lambda _: LearningPlanner((goals, steps[:2]), ([], steps[2:]), ([], [])))
    assert learned.ok and len(store.load_plan("wizard").steps) == 4
    page.goto((tmp_path / "p1.html").as_uri())
    result, mode, _ = run_wizard(no_llm)
    assert result.ok and mode == "replay" and page.input_value("#c") == "123"


def test_names_and_missing_automations(tmp_path):
    store = AutomationStore(tmp_path)
    with pytest.raises(AutomationError, match="invalid name"):
        store.create(Automation(name="Com Espaço", request="x", url="x", profile="x"))
    with pytest.raises(AutomationError, match="does not exist"):
        store.load("nope")
    assert store.names() == []



def test_replay_survives_a_renamed_button_with_the_same_meaning(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])))
    page.set_content(FORM.format(save="Gravar dados"))      # "gravar" means "salvar"
    result, mode, _ = run(store, page, no_llm)
    assert result.ok and mode == "replay"


# --------------------------------------------------------------------------
# Self-healing: when a saved step stops working, the automation recovers,
# corrects its saved plan and records the recovery, which can be undone
# --------------------------------------------------------------------------

from anchor.automations import undo_recovery  # noqa: E402

PAGE_V1 = """<html><body><label for="n">Nome</label><input id="n">
  <button onclick="document.getElementById('m').textContent='Pronto'">Enviar</button><p id="m" role="status"></p></body></html>"""
PAGE_V2 = PAGE_V1.replace(">Enviar<", ">Concluir cadastro<")     # the site changed the button


@pytest.fixture
def healing_store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="heal", request="cadastre a Maria", url="x", profile="x"))
    return s


def run_heal(store, page, make_planner, reports=None, **kw):
    page.set_default_timeout(1500)
    executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("heal")))
    report = reports.append if reports is not None else None
    return run_automation(store, "heal", page, executor, make_planner, report=report, **kw)


HEAL_GOALS = [Goal("g1", "cadastro feito", True)]
HEAL_PLAN = [("fill", "Nome", "Maria", "g1", None), ("click", "Enviar", None, "g1", None)]


def learn(store, page):
    page.set_content(PAGE_V1)
    result, _, _ = run_heal(store, page, lambda _: LearningPlanner((HEAL_GOALS, HEAL_PLAN), ([], [])))
    assert result.ok


def test_broken_step_is_healed_and_the_saved_plan_corrected(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V2)
    healer = LearningPlanner(([], [("click", "Concluir cadastro", None, "g1", None)]), ([], []))
    reports = []
    result, mode, run_id = run_heal(healing_store, page, lambda _: healer, reports)

    assert result.ok and mode == "replay" and result.llm_calls == 2
    assert any("planning the rest" in r for r in reports)
    plan = healing_store.load_plan("heal")
    assert [s.description for s in plan.steps] == ["Nome", "Concluir cadastro"]
    record = healing_store.recoveries("heal")[0]
    assert record["method"] == "replan" and record["run"] == run_id
    assert record["failed_step"]["description"] == "Enviar"
    assert [s["description"] for s in record["replaced_by"]] == ["Concluir cadastro"]
    assert record["effect_confirmed"] is True and record["confidence"][0]["resolved_by"] == "heuristic"
    assert [s["description"] for s in record["previous_plan"]["steps"]] == ["Nome", "Enviar"]


def test_after_healing_the_next_run_replays_the_corrected_plan_without_the_llm(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V2)
    run_heal(healing_store, page, lambda _: LearningPlanner(([], [("click", "Concluir cadastro", None, "g1", None)]), ([], [])))
    page.set_content(PAGE_V2)
    result, mode, _ = run_heal(healing_store, page, no_llm)
    assert result.ok and mode == "replay" and result.llm_calls == 0


def test_failed_healing_keeps_the_saved_plan(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V2)
    bad = [("click", "Botão que não existe", None, "g1", None)]
    result, _, _ = run_heal(healing_store, page, lambda _: LearningPlanner(([], bad), ([], bad), ([], bad)))
    assert not result.ok and result.message.startswith("the saved plan stopped working and the recovery did not succeed")
    assert [s.description for s in healing_store.load_plan("heal").steps] == ["Nome", "Enviar"]
    assert healing_store.recoveries("heal") == []


def test_no_heal_stops_like_before(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V2)
    result, _, _ = run_heal(healing_store, page, no_llm, heal=False)
    assert result.status == "failed" and result.message.startswith("the saved plan stopped working")


def test_undoing_a_correction_brings_the_previous_plan_back(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V2)
    run_heal(healing_store, page, lambda _: LearningPlanner(([], [("click", "Concluir cadastro", None, "g1", None)]), ([], [])))
    undo_recovery(healing_store, "heal", 1)
    assert [s.description for s in healing_store.load_plan("heal").steps] == ["Nome", "Enviar"]
    assert healing_store.recoveries("heal")[0]["undone"] is True
    with pytest.raises(ValueError, match="already undone"):
        undo_recovery(healing_store, "heal", 1)
    with pytest.raises(ValueError, match="no recovery #9"):
        undo_recovery(healing_store, "heal", 9)


class PickGreen:
    def choose(self, request):
        from anchor.engine.disambiguation import UserChoice
        return UserChoice("candidate", next(c.number for c in request.candidates if "verde" in c.near))

    def notify(self, message):
        pass


MUGS = """<html><body>
  <div><h3>Caneca azul</h3><button onclick="document.body.dataset.a=1">Adicionar</button></div>
  <div><h3>Caneca verde</h3><button onclick="document.body.dataset.v=1">Adicionar</button></div></body></html>"""


def test_user_choice_during_a_replay_is_recorded_and_can_be_undone(page, tmp_path):
    store = AutomationStore(tmp_path / "automations")
    store.create(Automation(name="mug", request="adicione a caneca", url="x", profile="x"))
    goals, plan = [Goal("g1", "caneca adicionada", True)], [("click", "Adicionar", None, "g1", None)]
    memory = ChoiceMemory(store.memory_path("mug"))
    page.set_default_timeout(1500)

    page.set_content(MUGS)
    executor = ActionExecutor(page, disambiguator=PickGreen(), memory=memory)
    run_automation(store, "mug", page, executor, lambda _: LearningPlanner((goals, plan), ([], [])), report=None)
    memory.clear()                                             # forget the learning run's choice

    page.set_content(MUGS)
    executor = ActionExecutor(page, disambiguator=PickGreen(), memory=memory)
    result, mode, _ = run_automation(store, "mug", page, executor, no_llm, report=None)
    assert result.ok and mode == "replay" and result.interventions == 1
    record = store.recoveries("mug")[0]
    assert record["method"] == "user" and record["step"]["description"] == "Adicionar"

    undo_recovery(store, "mug", 1, memory=memory)
    assert memory.entries == {}


def test_replay_messages_do_not_talk_about_planning(page, healing_store):
    learn(healing_store, page)
    page.set_content(PAGE_V1)
    reports = []
    run_heal(healing_store, page, no_llm, reports)
    text = "\n".join(reports)
    assert "Replaying the approved plan" in text and "Planning..." not in text


# --------------------------------------------------------------------------
# Parameters: {nome} in the request; the saved plan keeps the placeholders
# --------------------------------------------------------------------------

from anchor.automations.params import (  # noqa: E402
    find_parameters,
    read_rows,
    render,
    templatize_steps,
)

PEOPLE = """<html><body><label for="n">Nome</label><input id="n"><label for="c">CPF</label><input id="c">
  <button onclick="document.getElementById('m').textContent='Cadastro salvo de ' + document.getElementById('n').value">Salvar</button>
  <p id="m" role="status"></p></body></html>"""
P_GOALS = [Goal("g1", "{nome} cadastrada", True)]


@pytest.fixture
def param_store(tmp_path):
    s = AutomationStore(tmp_path / "automations")
    s.create(Automation(name="person", request="cadastre {nome}, CPF {cpf}, e salve", url="x", profile="x"))
    return s


def run_person(store, page, make_planner, values):
    page.set_default_timeout(1500)
    page.set_content(PEOPLE)
    executor = ActionExecutor(page, memory=ChoiceMemory(store.memory_path("person")))
    return run_automation(store, "person", page, executor, make_planner, report=None, params=values)


def learned_plan(nome, cpf):
    return [("fill", "Nome", nome, "g1", None), ("fill", "CPF", cpf, "g1", None), ("click", "Salvar", None, "g1", None)]


def test_create_finds_the_parameters(param_store):
    assert param_store.load("person").parameters == ["nome", "cpf"]
    assert find_parameters("salve {a} e {b} e {a}") == ["a", "b"]


def test_the_model_plans_with_the_real_values_and_the_plan_is_saved_with_placeholders(page, param_store):
    planner = LearningPlanner((P_GOALS, learned_plan("Maria Silva", "123.456.789-00")), ([], []))
    seen = []
    original = planner.plan
    planner.plan = lambda request, *a, **k: (seen.append(request), original(request, *a, **k))[1]
    result, _, _ = run_person(param_store, page, lambda _: planner, {"nome": "Maria Silva", "cpf": "123.456.789-00"})
    assert result.ok and seen[0] == "cadastre Maria Silva, CPF 123.456.789-00, e salve"
    steps = param_store.load_plan("person").steps
    assert [(s.description, s.value) for s in steps] == [("Nome", "{nome}"), ("CPF", "{cpf}"), ("Salvar", None)]


def test_replay_fills_the_placeholders_with_the_values_of_the_run(page, param_store):
    run_person(param_store, page, lambda _: LearningPlanner((P_GOALS, learned_plan("Maria Silva", "111")), ([], [])),
               {"nome": "Maria Silva", "cpf": "111"})
    result, mode, _ = run_person(param_store, page, no_llm, {"nome": "João Souza", "cpf": "222"})
    assert result.ok and mode == "replay" and result.llm_calls == 0
    assert page.input_value("#n") == "João Souza" and page.input_value("#c") == "222"
    assert "Cadastro salvo de João Souza" in page.inner_text("body")


def test_missing_and_unknown_parameters_are_refused(page, param_store):
    with pytest.raises(AutomationError, match="missing value for: cpf"):
        run_person(param_store, page, no_llm, {"nome": "Maria"})
    with pytest.raises(AutomationError, match="unknown parameter: idade"):
        run_person(param_store, page, no_llm, {"nome": "Maria", "cpf": "1", "idade": "30"})


def test_run_records_keep_the_placeholders_not_the_values(page, param_store):
    run_person(param_store, page, lambda _: LearningPlanner((P_GOALS, learned_plan("Maria Silva", "123.456.789-00")), ([], [])),
               {"nome": "Maria Silva", "cpf": "123.456.789-00"})
    text = (param_store.folder("person") / "runs").glob("*.json").__next__().read_text(encoding="utf-8")
    assert "123.456.789-00" not in text and "Maria Silva" not in text and "{cpf}" in text


def test_one_run_per_csv_row(page, param_store, tmp_path):
    (tmp_path / "people.csv").write_text("nome;cpf\nAna Lima;111\nBruno Reis;222\n", encoding="utf-8")
    rows = read_rows(tmp_path / "people.csv")
    assert rows == [{"nome": "Ana Lima", "cpf": "111"}, {"nome": "Bruno Reis", "cpf": "222"}]
    first = LearningPlanner((P_GOALS, learned_plan("Ana Lima", "111")), ([], []))
    results = [run_person(param_store, page, (lambda _: first) if i == 0 else no_llm, row)[0] for i, row in enumerate(rows)]
    assert all(r.ok for r in results) and results[1].llm_calls == 0
    assert page.input_value("#n") == "Bruno Reis"


def test_a_healed_plan_is_saved_with_placeholders(page, param_store):
    run_person(param_store, page, lambda _: LearningPlanner((P_GOALS, learned_plan("Ana Lima", "111")), ([], [])),
               {"nome": "Ana Lima", "cpf": "111"})
    page.set_default_timeout(1500)
    page.set_content(PEOPLE.replace('for="n">Nome', 'for="n">Funcionário'))     # the field was renamed
    healer = LearningPlanner(([], [("fill", "Funcionário", "Bruno Reis", "g1", None), ("fill", "CPF", "222", "g1", None),
                                   ("click", "Salvar", None, "g1", None)]), ([], []))
    executor = ActionExecutor(page, memory=ChoiceMemory(param_store.memory_path("person")))
    result, _, _ = run_automation(param_store, "person", page, executor, lambda _: healer, report=None,
                                  params={"nome": "Bruno Reis", "cpf": "222"})
    assert result.ok
    values = [(s.description, s.value) for s in param_store.load_plan("person").steps]
    assert ("Funcionário", "{nome}") in values and ("CPF", "{cpf}") in values
    record = param_store.recoveries("person")[0]
    assert all("Bruno" not in str(s) and "222" not in str(s) for s in record["replaced_by"])


def test_templatize_puts_placeholders_in_descriptions_too():
    steps = templatize_steps([Step("check", "Selecionar Ana Lima", None)], {"nome": "Ana Lima"})
    assert steps[0].description == "Selecionar {nome}"
    assert render("Excluir {nome}", {"nome": "Ana"}) == "Excluir Ana"


# --------------------------------------------------------------------------
# The user's notes: kept per automation, sent to the planner
# --------------------------------------------------------------------------

def test_notes_are_kept_and_only_the_most_recent_are_sent(store):
    for i in range(7):
        store.add_note("register", f"observação {i}")
    assert [n["number"] for n in store.notes("register")] == [1, 2, 3, 4, 5, 6, 7]
    assert store.recent_notes("register") == [f"observação {i}" for i in range(2, 7)]
    assert store.remove_note("register", 3) and not store.remove_note("register", 3)


class RecordingPlanner(LearningPlanner):
    def __init__(self, *plans):
        super().__init__(*plans)
        self.notes_seen = []

    def plan(self, request, url, page_elements=None, history=None, notes=None, **kw):
        self.notes_seen.append(notes)
        return super().plan(request, url, page_elements, history, **kw)


def test_the_planner_gets_the_notes_when_learning(page, store):
    store.add_note("register", "o botão Salvar fica no fim da página")
    page.set_content(FORM.format(save="Salvar"))
    planner = RecordingPlanner((GOALS, PLAN), ([], []))
    run(store, page, lambda _: planner)
    assert planner.notes_seen[0] == ["o botão Salvar fica no fim da página"]


def test_the_planner_gets_the_notes_when_healing(page, healing_store):
    learn(healing_store, page)
    healing_store.add_note("heal", "o botão agora se chama Concluir cadastro")
    page.set_content(PAGE_V2)
    healer = RecordingPlanner(([], [("click", "Concluir cadastro", None, "g1", None)]), ([], []))
    result, _, _ = run_heal(healing_store, page, lambda _: healer)
    assert result.ok and healer.notes_seen[0] == ["o botão agora se chama Concluir cadastro"]


def test_without_notes_the_message_to_the_model_does_not_change():
    from anchor.planner.prompt import user_message
    base = user_message("salve", "http://x", ["Botão Salvar"], None, "pt")
    assert user_message("salve", "http://x", ["Botão Salvar"], None, "pt", notes=[]) == base
    with_note = user_message("salve", "http://x", ["Botão Salvar"], None, "pt", notes=["fica no fim"])
    assert "Observações do usuário sobre esta tarefa" in with_note and "- fica no fim" in with_note


def test_notes_command(tmp_path, capsys):
    from anchor.automations.__main__ import main
    root = str(tmp_path)
    main(["--root", root, "create", "demo", "salve", "--url", "x", "--profile", "p"])
    assert main(["--root", root, "notes", "demo", "--add", "fica no fim"]) == 0
    main(["--root", root, "notes", "demo"])
    assert "fica no fim" in capsys.readouterr().out
    assert main(["--root", root, "notes", "demo", "--remove", "1"]) == 0
    assert main(["--root", root, "notes", "demo", "--remove", "1"]) == 1


# --------------------------------------------------------------------------
# Sensitive actions in saved automations: each decision is asked once and saved
# --------------------------------------------------------------------------

class Answer:
    def __init__(self, answer):
        self.answer, self.asked = answer, 0

    def confirm(self, request):
        self.asked += 1
        return self.answer


def test_an_allowed_action_is_not_asked_again(page, store):
    page.set_content(FORM.format(save="Salvar"))
    ask = Answer(True)
    result, _, _ = run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])), confirm=ask)
    assert result.ok and ask.asked == 1
    assert store.confirmations("register")[0]["decision"] == "allowed"
    page.set_content(FORM.format(save="Salvar"))
    result, _, _ = run(store, page, no_llm, confirm=ask)
    assert result.ok and ask.asked == 1                       # not asked again


def test_a_denied_action_stops_this_run_and_the_next_ones(page, store):
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])), confirm=Answer(True))
    store.forget_confirmation("register", 1)
    page.set_content(FORM.format(save="Salvar"))
    ask = Answer(False)
    result, _, _ = run(store, page, no_llm, confirm=ask)
    assert result.status == "cancelled" and result.denied and ask.asked == 1
    assert "Cadastro salvo" not in page.inner_text("body")
    page.set_content(FORM.format(save="Salvar"))
    result, _, _ = run(store, page, no_llm, confirm=Answer(True))
    assert result.denied                                      # the saved denial still holds
    assert store.runs("register")[-1]["denied"] is True


def test_just_pressing_enter_denies_only_this_time(page, store):
    from anchor.engine.sensitive import TerminalConfirmer
    page.set_content(FORM.format(save="Salvar"))
    run(store, page, lambda _: LearningPlanner((GOALS, PLAN), ([], [])), confirm=Answer(True))
    store.forget_confirmation("register", 1)
    page.set_content(FORM.format(save="Salvar"))
    enter = TerminalConfirmer(input_fn=lambda _: "", output=lambda _: None, interactive=True)
    result, _, _ = run(store, page, no_llm, confirm=enter)
    assert result.denied and store.confirmations("register") == []      # nothing saved
    page.set_content(FORM.format(save="Salvar"))
    result, _, _ = run(store, page, no_llm, confirm=Answer(True))
    assert result.ok                                                      # asked again, and allowed


def test_confirmations_command(tmp_path, capsys):
    from anchor.automations.__main__ import main
    root = str(tmp_path)
    main(["--root", root, "create", "demo", "salve", "--url", "x", "--profile", "p"])
    store = AutomationStore(tmp_path)
    store.add_confirmation("demo", {"action": "click", "element": "Salvar", "category": "submit", "decision": "denied"})
    main(["--root", root, "confirmations", "demo"])
    assert "Salvar" in capsys.readouterr().out
    assert main(["--root", root, "confirmations", "demo", "--forget", "1"]) == 0
    assert store.confirmations("demo") == []
    assert main(["--root", root, "confirmations", "demo", "--forget", "1"]) == 1
