"""
Is the request about reading data from the page?

Only then does the planner hear about the extraction actions (extract_table, and when to use
extract_text) and see the page's tables and lists in its summary. Every other request gets the
same prompt and the same page summary as before data extraction existed, so a feature for
reading cannot change how the planner handles, say, a registration (it did: with the extraction
lines always in the prompt, the 4B model stopped searching after filling the box, and the 9B one
left the contract type out of a registration).

A request is about reading when it has a verb for reading or handing data over ("extraia",
"exporte", "copie", "leia", "me passa", "export", "give me"), a question for a value ("qual",
"quanto", "what", "how many") or a noun for data ("tabela", "planilha", "CSV", "table"). A list
alone is not ("Selecione a Ana na lista").
"""

from __future__ import annotations

import re

_READING = re.compile(
    r"\b(extra[ií]\w*|export\w*|cop(ie|iar|ia|y)\b|leia|ler|read|me\s+(passa|passe|d[aáê]|mostr[ae])|"
    r"pass[ae]\s+(a|o|as|os)\s|mostre|give\s+me|show\s+me|tell\s+me|"
    r"qual|quais|quanto|quantos|quantas|what|which|how\s+(much|many)|"
    r"tabelas?|tables?|planilhas?|spreadsheets?|csv)\b", re.IGNORECASE)


def wants_data(request: str | None) -> bool:
    return bool(_READING.search(request or ""))
