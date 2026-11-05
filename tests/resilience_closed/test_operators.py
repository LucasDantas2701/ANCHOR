"""The closed set's operators keep every evaluation marker on the element it was on (made-up page)."""
import json
from pathlib import Path

import pytest

from eval.resilience.closed.generate import CATALOG, OPERATORS_JS

PAGE = (Path(__file__).parent / "page.html").resolve().as_uri()
TARGETS = ["e1", "e4", "e5"]
SNAPSHOT = """() => [...document.querySelectorAll('[data-eval]')].map(e => ({eval: e.getAttribute('data-eval'),
    tag: e.tagName, type: e.getAttribute('type') || '', inDom: document.body.contains(e)}))"""
PARAMS = {"L2.synonym": {"index": 0, "word": "Nome", "replacement": "designação"},
          "L5.inject-visible": {"text": "uma instrução", "ids": ["F01"]},
          "L5.inject-hidden": {"text": "uma instrução", "ids": ["I01"]}}
OPS = [o["id"] for o in CATALOG["operators"]]


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("seed", [1, 7, 20261024])
def test_every_marker_stays_on_one_element_of_the_same_kind_and_no_copy_carries_one(browser, op, seed):
    page = browser.new_context(java_script_enabled=False).new_page()
    page.goto(PAGE)
    before = {x["eval"]: x for x in page.evaluate(SNAPSHOT)}
    page.evaluate(OPERATORS_JS, ["apply", op, seed, "pt", TARGETS, PARAMS.get(op, {})])
    after = page.evaluate(SNAPSHOT)
    assert sorted(x["eval"] for x in after) == sorted(before)          # none lost, none copied, none moved to a second element
    for x in after:
        assert x["inDom"] and x["tag"] == before[x["eval"]]["tag"]
        if op != "L1.type":
            assert x["type"] == before[x["eval"]]["type"]
    page.close()


def test_the_probe_says_which_operators_apply_and_which_touch_the_plans_elements(browser):
    page = browser.new_context(java_script_enabled=False).new_page()
    page.goto(PAGE)
    probe = page.evaluate(OPERATORS_JS, ["probe", "", 1, "pt", TARGETS, {}])
    assert set(probe) == set(OPS)
    assert probe["L1.alt"]["applies"] and probe["L1.onclick"]["applies"] and not probe["L4.popup-deleted"]["applies"]
    assert probe["L1.value"]["applies"]                                  # the made-up page has option values
    assert any(c["pos"] == "noun" for c in probe["L2.synonym"]["candidates"])
    page.close()


def test_the_perturbed_page_still_works_with_its_own_scripts(browser):
    for op in ("L1.auto-id", "L1.manual-id", "L1.class", "L1.onclick", "L1.type", "L1.name"):
        page = browser.new_context(java_script_enabled=False).new_page()
        page.goto(PAGE)
        page.evaluate(OPERATORS_JS, ["apply", op, 5, "pt", TARGETS, {}])
        html = "<!doctype html>\n" + page.evaluate("() => document.documentElement.outerHTML")
        live = browser.new_page()
        live.set_content(html)
        live.locator('[data-eval~="e6"]').click()
        live.locator('[data-eval~="e4"]').click()
        assert live.evaluate("() => document.body.dataset.opened") == "1", op
        assert live.evaluate("() => document.body.dataset.sent") == "1", op
        live.close()
        page.close()
