"""
A run's outcome in plain words: a summary, and what to do next. The engine's own message is kept
as the detail; these sentences only say what it means for someone who does not program.
"""
from __future__ import annotations

import re

_RULES = [
    # (pattern in the engine's message, summary, hint)
    (r"could not generate the plan.*needs a value",
     "The AI could not make a plan for this page.",
     "Its plan typed into a field without saying what to type. If the page needs a login, say so in "
     "the request (\"log in to …\"): ANCHOR then waits for you to do it."),
    (r"could not generate the plan|invalid plan",
     "The AI could not make a plan for this page.",
     "Try saying the request in other words, or with the larger model."),
    (r"needs a login|login needed|log in",
     "This page needs you to log in.",
     "Run it again with the browser window shown, and log in when ANCHOR asks."),
    (r"password",
     "A password cannot go in a request.",
     "Write the request without it: when a page needs a login, ANCHOR waits for you to do it."),
    (r"cannot be done on this page|nothing to do",
     "This page has nothing for that request.",
     "Check the page's address, or say the request in other words."),
    (r"pending goals|not fulfilled|was not done",
     "Part of the request was not done.",
     "See what happened below: the last steps show where it stopped."),
    (r"connection|refused|ollama|timed out|timeout",
     "The AI could not be reached.",
     "Check that Ollama is open on this computer, then run it again."),
]


def explain(result: dict) -> dict:
    """The result, with "summary" and "hint" for the person."""
    state, message = result.get("state"), str(result.get("message", ""))
    if state == "checked":
        return {**result, "summary": "Done, and every step was checked.", "hint": ""}
    if state == "planned":                     # a plan only: nothing was done, so nothing was checked
        return {**result, "summary": "This is what the AI would do. Nothing was done on the page.", "hint": ""}
    if state == "stopped":
        return {**result, "summary": "Stopped.", "hint": "Nothing else was done after that point."}
    for pattern, summary, hint in _RULES:
        if re.search(pattern, message, re.IGNORECASE):
            return {**result, "summary": summary, "hint": hint}
    return {**result, "summary": message[:1].upper() + message[1:] if message else "It was not done.", "hint": ""}
