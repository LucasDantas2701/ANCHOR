"""No measured executor uses the evaluation's markers (data-eval): not the traditional script's selectors,
recorded on L0, and not the element lists the LLM-in-control agent and ANCHOR get."""
import json
from pathlib import Path

from anchor.engine.element_resolver import ElementResolver
from anchor.planner import page_elements
from eval.resilience.executors import numbered_elements, record_script

ROOT = Path(__file__).resolve().parents[2]
PAGE = (Path(__file__).parent / "page.html").resolve().as_uri()
L0 = ROOT / "eval" / "fixtures" / "resilience" / "L0"


def test_the_traditional_scripts_never_select_by_the_marker():
    scripts = json.loads((ROOT / "eval" / "plans" / "resilience_scripts.json").read_text(encoding="utf-8"))["scripts"]
    assert scripts and "data-eval" not in json.dumps(scripts)


def test_a_script_recorded_on_a_marked_page_does_not_use_the_marker(page):
    page.goto(PAGE)
    script = record_script(page, [["fill", "Nome completo", "Ana"], ["click", "Salvar cadastro", None]])
    assert script and "data-eval" not in json.dumps(script)


def test_the_element_lists_the_llm_agent_and_anchor_get_carry_no_marker(page):
    page.goto(PAGE)
    resolver = ElementResolver(page)
    lines, _ = numbered_elements(resolver)                                # the LLM-in-control agent's list
    planner_view = page_elements(resolver, request="salvar o cadastro", language="pt")   # ANCHOR's planner's list
    for seen in (json.dumps(lines, ensure_ascii=False), json.dumps(planner_view, ensure_ascii=False, default=str)):
        assert "data-eval" not in seen and "e4" not in seen.split('"')


def test_the_l0_pages_have_markers_so_the_tests_above_mean_something():
    assert all("data-eval" in f.read_text(encoding="utf-8") for f in L0.glob("*.html"))
