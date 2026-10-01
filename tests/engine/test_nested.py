"""Nested elements: a single candidate when only one of the two is interactive."""

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver

PRODUCTS = """<html><body>
  <div class="item"><a href="#p1"><div class="name">Sauce Labs Backpack</div></a> <span>$29.99</span></div>
  <div class="item"><a href="#p2"><div class="name">Sauce Labs Bike Light</div></a> <span>$9.99</span></div>
</body></html>"""


def test_link_and_the_name_inside_it_become_one_candidate(page):
    page.set_content(PRODUCTS)
    matches = ElementResolver(page).query("Sauce Labs Backpack", k=5, action="extract")
    tags = [m.tag for m in matches if "Backpack" in (m.text or "")]
    assert tags == ["a"]                      # the link stays; the name inside it is dropped


def test_extraction_is_not_ambiguous(page):
    page.set_content(PRODUCTS)
    result = ActionExecutor(page).extract_text("Sauce Labs Backpack")
    assert result.status == "success" and result.value == "Sauce Labs Backpack"


def test_two_nested_interactive_elements_stay_separate(page):
    page.set_content("""<html><body>
      <div role="button" onclick="window.x='card'" style="cursor:pointer">Caneca azul
        <button onclick="event.stopPropagation(); window.x='add'">Adicionar Caneca azul</button></div>
    </body></html>""")
    matches = ElementResolver(page).query("Caneca azul", k=5, action="click")
    assert {m.role for m in matches} >= {"button"} and len(matches) >= 2
