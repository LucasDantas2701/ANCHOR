from .constants import (
    ACTION_CONFLICT_DAMPING,
    ACTION_CONTENT_BONUS,
    ACTION_MISMATCH_DAMPING,
    ACTION_ROLE_WEIGHTS,
    DESTRUCTIVE_DAMPING,
    DISABLED_DAMPING,
    EXACT_NAME_BONUS,
    EXTRACT_TEXT_BONUS,
    OBJECT_CONTEXT_BONUS,
    OBJECT_MISMATCH_DAMPING,
)
from .tokenizer import (
    ACTION_WORDS_N,
    DESTRUCTIVE_N,
    KIND_WORDS_N,
    STOPWORDS_N,
    expand_actions,
    normalize_text,
    normalize_tokens,
    stem,
    tokenize,
)


def score_element(
    content: str,
    context: str,
    text: str,
    query: str,
    query_tokens: set[str],
    normalized_query_tokens: set[str],
    action_query_tokens: set[str],
    object_query_tokens: set[str],
    role: str,
    tag: str,
    action: str | None = None,
    synonyms: dict[str, set[str]] | None = None,
    state: dict | None = None,
    element_text: str | None = None,
) -> float:
    """
    Computes how relevant an element is
    to the description.
    """

    if not content or not query:
        return 0.0

    score = 0.0

    # Same space as the query: lowercase, no accents, compound expressions.
    content = normalize_text(content)
    context = normalize_text(context)
    text = normalize_text(text)

    content_tokens = tokenize(content)
    context_tokens = tokenize(context)

    normalized_content_tokens = normalize_tokens(
        content_tokens,
        synonyms,
    )

    normalized_context_tokens = normalize_tokens(
        context_tokens,
        synonyms,
    )

    # -------------------------------------------------
    # 1. Full-phrase match.
    # -------------------------------------------------

    if query in content:
        score += 0.35

    # -------------------------------------------------
    # 2. Direct match of the words in the element.
    # -------------------------------------------------

    if query_tokens:

        hits = 0.0

        for token in query_tokens:

            if token in content_tokens:
                hits += 1.0

            elif token in content:
                hits += 0.5

        score += (
            hits / len(query_tokens)
        ) * 0.25

    # -------------------------------------------------
    # 3. Semantic match in the element.
    # -------------------------------------------------

    if normalized_query_tokens:

        normalized_hits = (
            normalized_query_tokens
            & normalized_content_tokens
        )

        score += (
            len(normalized_hits)
            / len(normalized_query_tokens)
        ) * 0.20

    # -------------------------------------------------
    # 4. Context match.
    # -------------------------------------------------

    if normalized_query_tokens:

        context_hits = (
            normalized_query_tokens
            & normalized_context_tokens
        )

        score += (
            len(context_hits)
            / len(normalized_query_tokens)
        ) * 0.15

    # -------------------------------------------------
    # 4.5. Object match in the context.
    #
    # For actions, the object is the main discriminator
    # between similar elements.
    # -------------------------------------------------

    if object_query_tokens and action:

        # Each object token counts once: what is already in the
        # element itself is covered; the context is only checked
        # for what is missing. This avoids counting twice the
        # element's label, which also appears in the context text.
        own_hits = object_query_tokens & normalized_content_tokens
        context_hits = (
            (object_query_tokens - own_hits)
            & normalized_context_tokens
        )

        object_coverage = (
            len(own_hits | context_hits)
            / len(object_query_tokens)
        )

        if object_coverage == 0.0:
            score *= OBJECT_MISMATCH_DAMPING

        else:
            score += object_coverage * OBJECT_CONTEXT_BONUS

            if object_coverage == 1.0:
                score += 0.20

    # -------------------------------------------------
    # 4.6. Direct object match in the element
    # itself.
    # -------------------------------------------------

    if object_query_tokens:

        direct_object_hits = (
            object_query_tokens
            & normalized_content_tokens
        )

        if direct_object_hits:

            direct_object_coverage = (
                len(direct_object_hits)
                / len(object_query_tokens)
            )

            score += (
                direct_object_coverage
                * 0.20
            )

    # -------------------------------------------------
    # 5. Element type match.
    # -------------------------------------------------

    if stem(role) in normalized_query_tokens:
        score += 0.05

    elif stem(tag) in normalized_query_tokens:
        score += 0.05

    # -------------------------------------------------
    # 6. Preference for interactive elements.
    # -------------------------------------------------

    interactive_roles = {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "tab",
        "switch",
        "menuitem",
        "option",
        "spinbutton",
        "searchbox",
        "slider",
        "clickable",
    }

    if role in interactive_roles:
        score += 0.10

    elif tag in {
        "button",
        "a",
        "input",
        "select",
        "textarea",
    }:
        score += 0.10

    elif tag in {
        "div",
        "span",
        "p",
    }:
        score -= 0.05

    # -------------------------------------------------
    # 7. Alignment between the action and the content.
    # -------------------------------------------------

    if action_query_tokens:

        action_hits = (
            action_query_tokens
            & normalized_content_tokens
        )

        action_coverage = (
            len(action_hits)
            / len(action_query_tokens)
        )

        score += (
            action_coverage
            * ACTION_CONTENT_BONUS
        )

        if action_coverage == 0.0:
            score *= ACTION_MISMATCH_DAMPING

            # Conflicting verb: the element announces ANOTHER action
            # ("Add to cart" when the request was "open the cart").
            # Verbs come only from the element's label/text/hints,
            # never from a field's value ("Selecione" in a select).
            element_verbs = normalize_tokens(
                tokenize(element_text if element_text is not None else content),
                synonyms,
            ) & ACTION_WORDS_N

            if element_verbs and not (
                element_verbs & expand_actions(action_query_tokens)
            ):
                score *= ACTION_CONFLICT_DAMPING

    elif action == "click":
        # A request with no verb, which only names the element ("Consultor RPA"):
        # an element announcing a destructive action ("Fechar vaga de Consultor RPA")
        # is less likely than the item itself, and riskier.
        element_words = normalize_tokens(
            tokenize(element_text if element_text is not None else content),
            synonyms,
        ) | tokenize(element_text if element_text is not None else content)
        if element_words & DESTRUCTIVE_N:
            score *= DESTRUCTIVE_DAMPING

    # -------------------------------------------------
    # 8. Weight based on the action type.
    # -------------------------------------------------

    if action:

        action_weights = ACTION_ROLE_WEIGHTS.get(
            action,
            {}
        )

        if role in action_weights:
            score += action_weights[role]

        elif tag in action_weights:
            score += action_weights[tag]

    # -------------------------------------------------
    # 9. Text extraction.
    # -------------------------------------------------

    if action == "extract" and normalized_query_tokens:

        normalized_text_tokens = normalize_tokens(
            tokenize(text),
            synonyms,
        )

        text_hits = (
            normalized_query_tokens
            & normalized_text_tokens
        )

        text_coverage = (
            len(text_hits)
            / len(normalized_query_tokens)
        )

        score += (
            text_coverage
            * EXTRACT_TEXT_BONUS
        )

        normalized_text = " ".join(
            sorted(normalized_text_tokens)
        )

        normalized_query = " ".join(
            sorted(normalized_query_tokens)
        )

        if normalized_text == normalized_query:
            score += 0.35

        if text and query:

            text_normalized = " ".join(
                tokenize(text)
            )

            query_normalized = " ".join(
                tokenize(query)
            )

            if text_normalized == query_normalized:
                score += 0.25

    # -------------------------------------------------
    # 9.5. Identical name: the element's text (or label) is exactly what the
    # request names, with no extra words ("vagas de rpa em manaus" rather than
    # "vagas de rpa em manaus júnior").
    # -------------------------------------------------

    name_tokens = normalize_tokens(tokenize(element_text or ""), synonyms) - STOPWORDS_N
    named = object_query_tokens - KIND_WORDS_N
    # Not applied to extraction, which has its own exact-text rule (step 9).
    if action != "extract" and named and name_tokens and name_tokens - KIND_WORDS_N == named:
        score += EXACT_NAME_BONUS


    # -------------------------------------------------
    # 10. Element state.
    #
    # A disabled element cannot be the target of an
    # interaction (but it can be read during extraction).
    # Covered (obscured) elements are NOT penalized here:
    # the target may be behind a modal, and the right move
    # is to close the modal, not to pick another element.
    # -------------------------------------------------

    if state and state.get("disabled") and action != "extract":
        score *= DISABLED_DAMPING

    return max(0.0, score)