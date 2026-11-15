"""The fixed rules that loosen the recorder's checks (eval/relax_checks.py, decided on 14/11/2026), on made-up
requests: each rule applies only where the request leaves room, and the checks still run on a page."""
import pytest

import eval.relax_checks as rc


def fill(selector, value):
    return f'document.querySelector("{selector}").value === "{value}"'


def task(request, *checks):
    return {"id": "t", "request": request, "checks": list(checks), "reference": [["click", "x", None]]}


def test_a_dictated_text_stays_exact_but_ignores_capitals_accents_and_spaces():
    new, rules = rc.relax_task(task("Cadastre a Maria Silva, maria@exemplo.com", fill("#email", "maria@exemplo.com")), {"#email": "email"})
    assert rules == ["dictated"] and new["checks"][0].endswith('=== "maria@exemplo.com"') and "normalize" in new["checks"][0]


def test_a_free_text_checks_that_it_is_filled_and_has_the_shared_words():
    new, rules = rc.relax_task(task("Comente no chamado que o problema foi resolvido",
                                    fill("#comentario", "Problema resolvido, obrigado")), {"#comentario": "textarea"})
    assert rules == ["free_text"]
    assert new["checks"][0].endswith(".value.trim().length > 0")
    assert any('includes("proble")' in c for c in new["checks"]) and any('includes("resolv")' in c for c in new["checks"])
    assert not any("obrigado" in c for c in new["checks"])                # not in the request: not required


@pytest.mark.parametrize("request_text, offset", [("Reserve para amanhã", 1), ("para hoje", 0),
                                                  ("depois de amanhã de manhã", 2), ("book it for tomorrow", 1)])
def test_a_relative_date_is_computed_when_the_check_runs(request_text, offset):
    new, rules = rc.relax_task(task(request_text, fill("#dia", "2026-11-15")), {"#dia": "date"})
    assert rules == ["date"] and f"d.getDate() + {offset})" in new["checks"][0]


def test_a_weekday_is_the_next_one_and_a_fixed_date_stays():
    new, rules = rc.relax_task(task("Agende para a próxima sexta", fill("#dia", "2026-11-20")), {"#dia": "date"})
    assert rules == ["date"] and "((5 - d.getDay() + 7) % 7 || 7)" in new["checks"][0]
    same, none = rc.relax_task(task("Agende para 20/11", fill("#dia", "2026-11-20")), {"#dia": "date"})
    assert none == [] and same["checks"] == [fill("#dia", "2026-11-20")]


def test_a_period_of_the_day_becomes_a_range_and_amanha_is_not_the_morning():
    new, rules = rc.relax_task(task("Quero uma sala amanhã de manhã", fill("#ini", "21:35")), {"#ini": "time"})
    assert rules == ["period"] and "'06:00'" in new["checks"][0] and "'12:00'" in new["checks"][0]
    same, none = rc.relax_task(task("Quero uma sala amanhã às 15h", fill("#ini", "15:00")), {"#ini": "time"})
    assert none == []                                                    # "amanhã" alone is not "de manhã"


def test_an_unnamed_list_choice_becomes_any_option_and_a_named_one_stays():
    choose = 'document.querySelector("#sala").selectedOptions[0].text.trim() === "Amazonas (8 lugares)"'
    new, rules = rc.relax_task(task("Reserve uma sala", choose), {"#sala": "select"})
    assert rules == ["any_option"] and new["checks"] == ['document.querySelector("#sala").selectedIndex > 0']
    same, none = rc.relax_task(task("Reserve a sala Amazonas", choose), {"#sala": "select"})
    assert none == [] and same["checks"] == [choose]


def test_checks_written_by_hand_clicks_and_negatives_are_left_alone():
    checks = ["__clicked(\"form > button\")", "!__clicked('.danger')", "document.querySelector('#x').selectedIndex > 0"]
    new, rules = rc.relax_task(task("qualquer pedido", *checks), {})
    assert rules == [] and new["checks"] == checks


def test_the_loosened_checks_run_on_a_page(page):
    page.set_content('<input id="dia" type="date"><input id="ini" type="time"><textarea id="c"></textarea>'
                     '<select id="s"><option>Escolha</option><option>A</option></select>')
    request = "Amanhã de manhã: comente que foi resolvido"
    checks = rc.relax_task(task(request, fill("#dia", "2000-01-01"), fill("#ini", "21:00"), fill("#c", "Foi resolvido!"),
                                'document.querySelector("#s").selectedOptions[0].text.trim() === "A"'),
                           {"#dia": "date", "#ini": "time", "#c": "textarea", "#s": "select"})[0]["checks"]
    tomorrow = page.evaluate("(d => (d.setDate(d.getDate() + 1), d.toLocaleDateString('sv')))(new Date())")
    page.fill("#dia", tomorrow); page.fill("#ini", "09:30"); page.fill("#c", "  Já foi RESOLVIDO  "); page.select_option("#s", "A")
    assert all(page.evaluate(f"() => Boolean({c})") for c in checks)
    page.fill("#ini", "14:00")
    assert not all(page.evaluate(f"() => Boolean({c})") for c in checks)


def test_the_hand_written_forms_of_the_synthetic_set_follow_the_same_rules():
    """Single quotes, and a list option compared without trim or by its start (decided on 15/11/2026)."""
    dictated, rules = rc.relax_task(task("Cadastre Ana Lima", "document.querySelector('#nome').value === 'Ana Lima'"), {"#nome": "text"})
    assert rules == ["dictated"] and dictated["checks"][0].endswith('=== "ana lima"')
    for check in ("document.querySelector('#sala').selectedOptions[0].text === 'Negro (4 lugares)'",
                  "document.querySelector('#sala').selectedOptions[0].text.startsWith('Negro')"):
        new, rules = rc.relax_task(task("Reserve uma sala", check), {"#sala": "select"})
        assert rules == ["any_option"] and new["checks"] == ['document.querySelector("#sala").selectedIndex > 0']
        same, none = rc.relax_task(task("Reserve a sala Negro", check), {"#sala": "select"})
        assert none == [] and same["checks"] == [check]
    escaped, rules = rc.relax_task(task("Escreva D'Ávila", "document.querySelector('#n').value === 'D\\'Ávila'"), {"#n": "text"})
    assert rules == ["dictated"] and escaped["checks"][0].endswith('=== "d\'avila"')
