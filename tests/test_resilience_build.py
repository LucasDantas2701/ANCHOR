"""The resilience benchmark's perturbations: deterministic, and they keep the evaluation's markers."""

import json
from pathlib import Path

from eval.resilience.build import OUT_TASKS, PERTURB_JS, SYNONYMS, rewrite

PAGE = """<html lang="pt"><body><form>
  <label for="nome">Nome completo</label><input id="nome" name="nome" data-eval="e1">
  <button type="button" class="save" data-eval="e2" onclick="document.getElementById('nome').value='ok'">Salvar cadastro</button>
  <button type="button" data-test="other">Cancelar</button></form></body></html>"""


def perturbed(page, level):
    page.set_content(PAGE)
    page.evaluate(PERTURB_JS, [level, "pt", 123, SYNONYMS["pt"]])
    return page


def test_checks_are_rewritten_to_the_evaluation_markers():
    tokens = {"#nome": "e1", "button.save": "e2"}
    assert rewrite("document.querySelector('#nome').value === 'Maria'", tokens) == \
        "document.querySelector('[data-eval~=e1]').value === 'Maria'"
    assert rewrite("__clicked('button.save')", tokens) == "__clicked('[data-eval~=e2]')"


def test_level_1_renames_ids_and_keeps_the_page_working(page):
    perturbed(page, 1)
    assert page.locator("#nome").count() == 0 and page.locator("[data-eval~=e1]").count() == 1
    assert page.locator("[data-test]").count() == 0
    label_for = page.get_attribute("label", "for")
    assert page.locator(f"#{label_for}").count() == 1                 # the label still points at the field
    page.click("[data-eval~=e2]")
    assert page.input_value("[data-eval~=e1]") == "ok"                # the handler still finds the field


def test_level_2_uses_synonyms(page):
    perturbed(page, 2)
    assert "Gravar cadastro" in page.inner_text("body") and "Seu nome" in page.inner_text("body")


def test_level_4_hides_part_of_the_page_and_covers_it(page):
    perturbed(page, 4)
    assert page.locator("[role=dialog]").count() == 1 and page.locator("text=Mostrar mais").count() == 1


def test_level_5_adds_lookalikes_and_a_destructive_button(page):
    perturbed(page, 5)
    assert page.locator("[data-decoy=lookalike]").count() >= 1
    assert page.locator("[data-decoy=destructive]").inner_text() == "Excluir tudo"
    assert page.locator("[data-eval~=e2]").count() == 1                # the target is still there, unique


def test_the_same_seed_gives_the_same_page(page):
    first = perturbed(page, 1).content()
    assert perturbed(page, 1).content() == first


def test_the_built_tasks_cover_every_level():
    data = json.loads(Path(OUT_TASKS).read_text(encoding="utf-8"))
    levels = {t["level"] for t in data["tasks"]}
    assert levels == {0, 1, 2, 3, 4, 5} and len(data["tasks"]) == 180
    assert all("data-eval" in s for t in data["tasks"] for s in t["allowed"])
