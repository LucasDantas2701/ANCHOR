"""Interface language: English by default, Portuguese with ANCHOR_LANG=pt or set_language."""

import pytest

from anchor import i18n


def test_english_by_default(monkeypatch):
    monkeypatch.delenv("ANCHOR_LANG", raising=False)
    i18n.set_language(None)
    assert i18n.t("kind.button") == "Button"


def test_portuguese_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANCHOR_LANG", "pt")
    i18n.set_language(None)
    assert i18n.t("kind.button") == "Botão"


def test_set_language_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("ANCHOR_LANG", "pt")
    i18n.set_language("en")
    try:
        assert i18n.t("mem.empty") == "No remembered choices."
    finally:
        i18n.set_language(None)


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError):
        i18n.set_language("fr")


def test_every_message_exists_in_both_languages():
    missing = [key for key, entry in i18n.MESSAGES.items() if set(entry) != set(i18n.SUPPORTED)]
    assert missing == []


def test_the_model_facing_summary_keeps_portuguese_kinds(page):
    from anchor.engine.element_resolver import ElementResolver
    from anchor.planner import page_elements
    page.set_content('<html><body><button>Salvar</button></body></html>')
    assert page_elements(ElementResolver(page)) == ['Botão "Salvar"']
