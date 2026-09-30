"""Descreve um Match para uma pessoa não-técnica."""

from anchor.engine.element_resolver import Match

from .types import CandidateView

KIND = {
    "button": "Botão", "link": "Link", "textbox": "Campo de texto", "searchbox": "Campo de busca",
    "checkbox": "Caixa de marcação", "radio": "Opção", "combobox": "Lista de opções",
    "listbox": "Lista de opções", "switch": "Chave liga/desliga", "tab": "Aba",
    "menuitem": "Item de menu", "option": "Opção", "slider": "Controle deslizante",
    "spinbutton": "Campo numérico", "clickable": "Área clicável",
}


def describe(match: Match, number: int) -> CandidateView:
    # Sem rótulo, texto nem pista visual: o data-testid costuma ser descritivo
    # ("shopping-cart-link" → "shopping cart link").
    test_id = " ".join(match.test_id.replace("-", " ").replace("_", " ").split())
    name = match.label or match.text or match.hint or match.value or test_id or "(sem texto)"

    # Texto curto demais para identificar o elemento (ex.: o contador "2" do
    # carrinho): junta a pista visual do ícone ("shopping cart 2").
    if match.hint and name == match.text and len(name) <= 3:
        name = f"{match.hint} {name}"
    near = " ".join((match.context or "").split())

    # Tira o próprio nome do elemento do "perto de" (sem diferenciar maiúsculas).
    start = near.lower().find(name.lower())
    if start >= 0:
        near = " ".join((near[:start] + near[start + len(name):]).split())
    if len(near) > 60:
        near = near[:57].rstrip() + "..."
    return CandidateView(
        number=number,
        kind=KIND.get(match.role, "Elemento"),
        name=name[:60],
        near=near,
    )
