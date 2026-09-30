RESOLVER_ACTION_MAP = {
    "click": "click",
    "hover": "click",
    "check": "check",       # was "click" — now uses the dedicated weights (checkbox/switch/radio)
    "uncheck": "check",     # was "click" — uncheck uses the same role profile as check
    "press": "click",
    "fill": "fill",
    "select": "select",     # was "fill" — now uses the dedicated weights (option/combobox/listbox)
    "extract_text": "extract",
    "extract_attribute": "extract",
    "extract_value": "extract",
}

# Calibrated with eval/run.py --sweep on the dev set (52 cases, commit b325f58+).
# The gap is RELATIVE: (1st score - 2nd score) / 1st score.
# Being relative, it does not depend on the score's scale, which changes when the rules change (B6).
DEFAULT_MIN_SCORE = 0.40
DEFAULT_AMBIGUITY_GAP = 0.04
DEFAULT_K = 5