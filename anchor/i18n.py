"""
User-facing messages in English (default) or Portuguese.

The language comes from, in order: set_language(), the ANCHOR_LANG
environment variable ("en" or "pt"), or English.

This covers what the *user* reads (terminal prompts, reports). What the
*model* reads (the planner prompt, the page summary) has its own language
setting, in anchor.planner, so that changing the interface language does not
change the model's behavior.
"""

from __future__ import annotations

import os

SUPPORTED = ("en", "pt")
DEFAULT_LANGUAGE = "en"

_current: str | None = None


def set_language(language: str | None) -> None:
    """Sets the interface language for this process (None goes back to the default)."""
    global _current
    if language is not None and language not in SUPPORTED:
        raise ValueError(f"unsupported language {language!r}; use one of {', '.join(SUPPORTED)}")
    _current = language


def get_language() -> str:
    if _current:
        return _current
    env = (os.environ.get("ANCHOR_LANG") or "").strip().lower()[:2]
    return env if env in SUPPORTED else DEFAULT_LANGUAGE


def t(key: str, language: str | None = None, **values) -> str:
    """The message for key, in the given language (or the current one)."""
    entry = MESSAGES[key]
    text = entry.get(language or get_language()) or entry[DEFAULT_LANGUAGE]
    return text.format(**values) if values else text


MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ element kinds
    "kind.button": {"en": "Button", "pt": "Botão"},
    "kind.link": {"en": "Link", "pt": "Link"},
    "kind.textbox": {"en": "Text field", "pt": "Campo de texto"},
    "kind.searchbox": {"en": "Search field", "pt": "Campo de busca"},
    "kind.checkbox": {"en": "Checkbox", "pt": "Caixa de marcação"},
    "kind.radio": {"en": "Option", "pt": "Opção"},
    "kind.combobox": {"en": "Dropdown", "pt": "Lista de opções"},
    "kind.listbox": {"en": "Dropdown", "pt": "Lista de opções"},
    "kind.switch": {"en": "Toggle switch", "pt": "Chave liga/desliga"},
    "kind.tab": {"en": "Tab", "pt": "Aba"},
    "kind.menuitem": {"en": "Menu item", "pt": "Item de menu"},
    "kind.option": {"en": "Option", "pt": "Opção"},
    "kind.slider": {"en": "Slider", "pt": "Controle deslizante"},
    "kind.spinbutton": {"en": "Number field", "pt": "Campo numérico"},
    "kind.clickable": {"en": "Clickable area", "pt": "Área clicável"},
    "kind.other": {"en": "Element", "pt": "Elemento"},
    "element.no_text": {"en": "(no text)", "pt": "(sem texto)"},
    # ------------------------------------------------------------ disambiguation (terminal)
    "verb.click": {"en": "click", "pt": "clicar"},
    "verb.hover": {"en": "hover over", "pt": "passar o mouse"},
    "verb.check": {"en": "check", "pt": "marcar"},
    "verb.uncheck": {"en": "uncheck", "pt": "desmarcar"},
    "verb.press": {"en": "press a key on", "pt": "pressionar uma tecla em"},
    "verb.fill": {"en": "fill in", "pt": "preencher"},
    "verb.select": {"en": "choose an option in", "pt": "escolher uma opção em"},
    "verb.extract_text": {"en": "read the text of", "pt": "ler o texto de"},
    "verb.extract_attribute": {"en": "read", "pt": "ler"},
    "verb.extract_value": {"en": "read the value of", "pt": "ler o valor de"},
    "dis.where_browser": {"en": "in the browser window", "pt": "na janela do navegador"},
    "dis.where_image": {"en": "in the image", "pt": "na imagem"},
    "dis.ambiguous": {"en": 'I found more than one possible element for: "{description}"',
                      "pt": 'Encontrei mais de um elemento possível para: "{description}"'},
    "dis.numbered": {"en": "The candidates are numbered {where}:", "pt": "Os candidatos estão numerados {where}:"},
    "dis.not_found": {"en": 'I could not find where to {verb}: "{description}"',
                      "pt": 'Não encontrei onde {verb}: "{description}"'},
    "dis.point_hint": {"en": "If you can see the element, type C and click it in the browser.",
                       "pt": "Se você está vendo o elemento, digite C e clique nele no navegador."},
    "dis.number_hint": {"en": "If it is one of these (numbered {where}), type the number:",
                        "pt": "Se for um destes (numerados {where}), digite o número:"},
    "dis.near": {"en": "  (near: {near})", "pt": "  (perto de: {near})"},
    "dis.none_of_these": {"en": "If it is none of these, type C and click the right element in the browser.",
                          "pt": "Se não for nenhum destes, digite C e clique no elemento certo no navegador."},
    "dis.opt_point": {"en": "C to click it yourself in the browser", "pt": "C para clicar você mesmo no navegador"},
    "dis.opt_number": {"en": "a number from 1 to {count}", "pt": "número de 1 a {count}"},
    "dis.opt_skip": {"en": "S to skip this step", "pt": "P para pular este passo"},
    "dis.prompt": {"en": "Type {options}: ", "pt": "Digite {options}: "},
    "dis.invalid": {"en": "Answer not recognized, please try again.", "pt": "Resposta não reconhecida, tente de novo."},
    "dis.banner": {"en": "Click the element the assistant should use", "pt": "Clique no elemento que o assistente deve usar"},
    "dis.image_saved": {"en": "(image saved at {path})", "pt": "(imagem salva em {path})"},
    # ------------------------------------------------------------ choice memory (terminal)
    "mem.help": {"en": "Reviews the choice memory.", "pt": "Revisa a memória das escolhas."},
    "mem.help_file": {"en": "memory file (e.g. memory/demo.json)", "pt": "arquivo da memória (ex.: memory/demo.json)"},
    "mem.help_list": {"en": "shows the remembered choices", "pt": "mostra as escolhas memorizadas"},
    "mem.help_forget": {"en": "forgets choices by the number shown by 'list'",
                        "pt": "esquece escolhas pelo número mostrado em 'listar'"},
    "mem.help_clear": {"en": "forgets all choices", "pt": "esquece todas as escolhas"},
    "mem.help_yes": {"en": "does not ask for confirmation", "pt": "não pede confirmação"},
    "mem.empty": {"en": "No remembered choices.", "pt": "Nenhuma escolha memorizada."},
    "mem.count": {"en": "{count} remembered choice(s) in {path}:\n", "pt": "{count} escolha(s) memorizada(s) em {path}:\n"},
    "mem.step": {"en": '[{number}] Step: "{description}" ({action})', "pt": '[{number}] Passo: "{description}" ({action})'},
    "mem.element": {"en": "    Element: {element}", "pt": "    Elemento: {element}"},
    "mem.page": {"en": "    Page: {url}", "pt": "    Página: {url}"},
    "mem.used": {"en": "    Used {uses} time(s), last on {last}\n", "pt": "    Usada {uses} vez(es), última em {last}\n"},
    "mem.near": {"en": ", near: {near}", "pt": ", perto de: {near}"},
    "mem.no_file": {"en": "File not found: {path}", "pt": "Arquivo não encontrado: {path}"},
    "mem.invalid": {"en": "Invalid number(s): {numbers}. Use 'list' to see the numbers.",
                    "pt": "Número(s) inválido(s): {numbers}. Use 'listar' para ver os números."},
    "mem.forgotten": {"en": 'Forgotten [{number}]: "{description}" → {element}',
                      "pt": 'Esquecida [{number}]: "{description}" → {element}'},
    "mem.will_ask": {"en": "On the next run, the assistant will ask again on these steps.",
                     "pt": "Na próxima execução, o assistente vai perguntar de novo nesses passos."},
    "mem.confirm": {"en": "Forget all {total} choices? (y/n) ", "pt": "Esquecer as {total} escolhas? (s/n) "},
    "mem.nothing_deleted": {"en": "Nothing was deleted.", "pt": "Nada foi apagado."},
    "mem.cleared": {"en": "{total} choice(s) forgotten.", "pt": "{total} escolha(s) esquecida(s)."},
    # ------------------------------------------------------------ login and demo
    "session.not_logged_in": {"en": "You are not logged in.", "pt": "Usuário não está logado."},
    "session.log_in": {"en": "Please log in in the browser.", "pt": "Faça o login no navegador."},
    "session.detected": {"en": "Login detected!", "pt": "Login detectado!"},
    "session.logged_in": {"en": "You are already logged in.", "pt": "Usuário já está logado."},
    "demo.step": {"en": "- {description}: {status} (by: {by})", "pt": "- {description}: {status} (por: {by})"},
    "demo.stopped": {"en": "  Step not completed; stopping.", "pt": "  Passo não concluído; encerrando."},
    "demo.starting": {"en": "Starting the automation...", "pt": "Iniciando automação..."},
    "demo.press_enter": {"en": "Press ENTER to finish...", "pt": "Pressione ENTER para encerrar..."},
}
