"""
Text normalization for the Resolver.

All text (the query, the elements' content and context, the dictionaries)
goes through the same pipeline, so both sides are comparable:

    text
      ↓  lowercase + accent removal            "Devoluções" → "devolucoes"
      ↓  compound expressions (B5)             "lista de desejos" → "wishlist"
      ↓  tokenization
      ↓  light PT/EN stem                      "devolucoes" → "devoluca"
    tokens

The stemmer is simple on purpose (inspired by RSLP, Orengo & Huyck, 2001):
it removes the plural and then one verb/noun ending. It does not need to
produce correct words, only to bring variations of the same word to the same
stem, applied equally to the query and to the page.
"""

import re
import unicodedata
from functools import lru_cache

from .constants import (
    ACTION_EQUIVALENTS,
    ACTION_WORDS,
    DESTRUCTIVE_WORDS,
    KIND_WORDS,
    STOPWORDS,
    STRUCTURAL_WORDS,
    SYNONYMS,
)

TOKEN_RE = re.compile(r"[^a-z0-9]+")

# Plural: applied first, at most one rule.
_PLURAL = (
    ("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"),
    ("ois", "ol"), ("ns", "m"), ("res", "r"), ("zes", "z"), ("s", ""),
)

# Verb and gender endings: after the plural, at most one rule.
_SUFFIXES = (
    "amento", "imento", "ando", "endo", "indo",
    "ado", "ada", "ido", "ida", "ar", "er", "ir", "e", "a", "o",
)

_MIN_STEM = 3


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@lru_cache(maxsize=100_000)
def stem(token: str) -> str:
    if len(token) <= _MIN_STEM or token.isdigit():
        return token

    for suffix, replacement in _PLURAL:
        if (
            token.endswith(suffix)
            and not token.endswith("ss")
            and len(token) - len(suffix) >= _MIN_STEM
        ):
            token = token[: -len(suffix)] + replacement
            break

    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= _MIN_STEM:
            return token[: -len(suffix)]

    return token


# ----------------------------------------------------------------------
# Compound expressions (fixes bug B5)
# ----------------------------------------------------------------------

def _basic(text: str) -> str:
    return strip_accents(text.lower())


_PHRASES = {
    _basic(key): value
    for key, value in SYNONYMS.items()
    if " " in key or "-" in key
}

_PHRASE_RE = (
    re.compile(
        r"\b(" + "|".join(
            re.escape(p) for p in sorted(_PHRASES, key=len, reverse=True)
        ) + r")\b"
    )
    if _PHRASES else None
)


def normalize_text(text: str) -> str:
    """Lowercase, no accents, with compound expressions replaced."""
    text = _basic(text or "")
    if _PHRASE_RE:
        text = _PHRASE_RE.sub(lambda m: _PHRASES[m.group(1)], text)
    return text


# ----------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------

def _stem_words(text: str) -> set[str]:
    return {stem(t) for t in TOKEN_RE.split(_basic(text)) if t}


def tokenize(text: str) -> set[str]:
    return {
        stem(token)
        for token in TOKEN_RE.split(normalize_text(text))
        if token
    }


def build_synonyms(raw: dict[str, str]) -> dict[str, set[str]]:
    """Normalizes keys and values of a one-word synonym dictionary."""
    out: dict[str, set[str]] = {}
    for key, value in raw.items():
        keys = _stem_words(key)
        if len(keys) != 1:
            continue  # compound expressions are handled by normalize_text
        out[keys.pop()] = _stem_words(value)
    return out


# Dictionaries already normalized (same space as the tokens).
SYNONYMS_N = build_synonyms(SYNONYMS)
ACTION_WORDS_N = {stem(_basic(w)) for w in ACTION_WORDS if " " not in w}
STOPWORDS_N = {stem(_basic(w)) for w in STOPWORDS}
STRUCTURAL_WORDS_N = {stem(_basic(w)) for w in STRUCTURAL_WORDS}

DESTRUCTIVE_N = {stem(_basic(w)) for w in DESTRUCTIVE_WORDS}
KIND_WORDS_N = {stem(_basic(w)) for w in KIND_WORDS}

_EQUIV_N = [{stem(w) for w in group} for group in ACTION_EQUIVALENTS]


def expand_actions(actions: set[str]) -> set[str]:
    """Adds the equivalent verbs (select → choose, pick...)."""
    out = set(actions)
    for group in _EQUIV_N:
        if out & group:
            out |= group
    return out


def normalize_tokens(
    tokens: set[str],
    extra: dict[str, set[str]] | None = None,
) -> set[str]:
    """
    Replaces each token with its synonym(s).

    extra:
        Vocabulary specific to an automation/site
        (e.g. "mochila" → backpack), already normalized with build_synonyms().
    """
    normalized: set[str] = set()
    for token in tokens:
        if extra and token in extra:
            normalized |= extra[token]
        elif token in SYNONYMS_N:
            normalized |= SYNONYMS_N[token]
        else:
            normalized.add(token)
    return normalized


def extract_object_tokens(
    normalized_query_tokens: set[str],
    action_query_tokens: set[str],
) -> set[str]:
    """
    Extracts the semantically relevant tokens
    from the query.
    """

    return (
        normalized_query_tokens
        - action_query_tokens
        - STRUCTURAL_WORDS_N
        - STOPWORDS_N
    )
