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
    (r"click was blocked|is on top of the element|intercepts pointer events",
     "A click could not happen: something on the page was on top of the element.",
     "Watch it run to see what is in the way (a panel, a menu, a pop-up); then Try again."),
    (r"never became ready|Timeout \d+ms exceeded",
     "A click could not happen: the element was not ready.",
     "The page may still have been loading, or the element was hidden. Watch it run, then Try again."),
    (r"end check kept finding steps",
     "ANCHOR kept finding more to do, so it stopped.",
     "See what was done below. A request with \"all\" or \"every\" may need a clearer end, like \"the first five\"."),
    (r"ollama|could not reach the model|connection refused|failed to establish|max retries",
     "The AI could not be reached.",
     "Check that Ollama is open on this computer, then run it again."),
]

# "3 failed attempts; last problem: click Vagas — <why>": the summary says what happened; the
# last problem, in its own words, becomes the hint.
_ATTEMPTS = re.compile(r"(\d+) failed attempts; last problem: (.+?) — (.+)$")


def explain(result: dict) -> dict:
    """The result, with "summary" and "hint" for the person."""
    state, message = result.get("state"), str(result.get("message", ""))
    if state == "checked":
        return {**result, "summary": "Done, and every step was checked.", "hint": ""}
    if state == "planned":                     # a plan only: nothing was done, so nothing was checked
        return {**result, "summary": "This is what the AI would do. Nothing was done on the page.", "hint": ""}
    if state == "stopped":
        return {**result, "summary": "Stopped.", "hint": "Nothing else was done after that point."}
    attempts = _ATTEMPTS.search(message)
    if attempts:
        count, step, why = attempts.groups()
        for pattern, summary, hint in _RULES:
            if re.search(pattern, why, re.IGNORECASE):
                return {**result, "summary": f"ANCHOR tried {count} times and stopped. {summary}", "hint": hint}
        return {**result, "summary": f"ANCHOR tried {count} times and stopped.",
                "hint": f"The last step it tried was \"{step}\": {why[:1].lower() + why[1:]}."}
    for pattern, summary, hint in _RULES:
        if re.search(pattern, message, re.IGNORECASE):
            return {**result, "summary": summary, "hint": hint}
    return {**result, "summary": message[:1].upper() + message[1:] if message else "It was not done.", "hint": ""}
