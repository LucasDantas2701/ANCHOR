RESOLVER_ACTION_MAP = {
    "click": "click",
    "hover": "click",
    "check": "check",       # antes: "click" — agora aproveita os pesos dedicados (checkbox/switch/radio)
    "uncheck": "check",     # antes: "click" — uncheck usa o mesmo perfil de role que check
    "press": "click",
    "fill": "fill",
    "select": "select",     # antes: "fill" — agora aproveita os pesos dedicados (option/combobox/listbox)
    "extract_text": "extract",
    "extract_attribute": "extract",
    "extract_value": "extract",
}

# Calibrados com eval/run.py --sweep no conjunto dev (52 casos, commit b325f58+).
# O gap é RELATIVO: (score do 1º - score do 2º) / score do 1º.
# Relativo não depende da escala do score, que muda quando as regras mudam (B6).
DEFAULT_MIN_SCORE = 0.40
DEFAULT_AMBIGUITY_GAP = 0.04
DEFAULT_K = 5