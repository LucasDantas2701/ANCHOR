"""Elementos aninhados: um candidato só quando apenas um dos dois é interativo."""

from app.engine.action_executor import ActionExecutor
from app.engine.element_resolver import ElementResolver

PRODUCTS = """<html><body>
  <div class="item"><a href="#p1"><div class="name">Sauce Labs Backpack</div></a> <span>$29.99</span></div>
  <div class="item"><a href="#p2"><div class="name">Sauce Labs Bike Light</div></a> <span>$9.99</span></div>
</body></html>"""


def test_link_e_nome_dentro_dele_viram_um_candidato(page):
    page.set_content(PRODUCTS)
    matches = ElementResolver(page).query("Sauce Labs Backpack", k=5, action="extract")
    tags = [m.tag for m in matches if "Backpack" in (m.text or "")]
    assert tags == ["a"]                      # o link fica; o nome dentro dele sai


def test_extracao_nao_fica_ambigua(page):
    page.set_content(PRODUCTS)
    result = ActionExecutor(page).extract_text("Sauce Labs Backpack")
    assert result.status == "success" and result.value == "Sauce Labs Backpack"


def test_dois_interativos_aninhados_continuam_distintos(page):
    page.set_content("""<html><body>
      <div role="button" onclick="window.x='card'" style="cursor:pointer">Caneca azul
        <button onclick="event.stopPropagation(); window.x='add'">Adicionar Caneca azul</button></div>
    </body></html>""")
    matches = ElementResolver(page).query("Caneca azul", k=5, action="click")
    assert {m.role for m in matches} >= {"button"} and len(matches) >= 2
