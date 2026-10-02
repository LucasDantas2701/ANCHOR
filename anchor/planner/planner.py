"""Planner: user request → list of steps, using an LLM."""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Protocol

from openai import BadRequestError

from anchor.i18n import t

from .language import AUTO, DEFAULT_PROMPT_LANGUAGE, PROMPT_LANGUAGES, detect_language, mt
from .plan import (
    PLAN_SCHEMA,
    Plan,
    PlanError,
    check_goals,
    check_request,
    check_values_from_request,
    parse_goals,
    parse_plan,
)
from .prompt import system_prompt, user_message


class Planner(Protocol):
    def plan(
        self,
        request: str,
        url: str,
        page_elements: Optional[list[str]] = None,
        history: Optional[list[str]] = None,
        known_goals: Optional[set[str]] = None,
        notes: Optional[list[str]] = None,
    ) -> Plan: ...


def _extract_json(text: str, language: str = DEFAULT_PROMPT_LANGUAGE) -> object:
    """Accepts plain JSON or JSON inside ```json ... ``` (local models sometimes do this)."""
    text = (text or "").strip()
    # "Thinking" models sometimes put their reasoning in the answer: drop it.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(mt("plan.not_json", language, msg=exc.msg)) from exc


class LLMPlanner:
    """
    client: a client with the OpenAI SDK interface (client.chat.completions.create).
    max_attempts: if the model returns an invalid plan, it gets the error and tries again.
    extra_body: extra parameters passed to the server on every call
                (e.g. to turn off the reasoning of a "thinking" model).
    language: the prompt's language, "pt" (default, the measured one), "en", or "auto"
              (it follows each request's language). The agent writes the execution
              history for the model in the same language (see language_for).
    """

    def __init__(self, client, model: str, temperature: float = 0.0, max_attempts: int = 2, seed: int = 7,
                 extra_body: Optional[dict] = None, language: str = DEFAULT_PROMPT_LANGUAGE):
        if language not in PROMPT_LANGUAGES + (AUTO,):
            raise ValueError(f"unsupported prompt language {language!r}; "
                             f"use one of {', '.join(PROMPT_LANGUAGES + (AUTO,))}")
        self.language = language
        self.last_attempts: list[tuple[str, str]] = []   # (the model's answer, why it was refused)
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_attempts = max_attempts
        self.seed = seed
        self.extra_body = extra_body
        self._schema_supported = True

    def _call(self, messages: list[dict]):
        kwargs = dict(model=self.model, messages=messages, temperature=self.temperature, seed=self.seed)
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        if self._schema_supported:
            try:
                return self.client.chat.completions.create(
                    **kwargs,
                    response_format={"type": "json_schema",
                                     "json_schema": {"name": "plano", "schema": PLAN_SCHEMA, "strict": True}},
                )
            except BadRequestError:
                self._schema_supported = False  # server without schema support: ask for plain JSON
        return self.client.chat.completions.create(**kwargs, response_format={"type": "json_object"})

    def language_for(self, request: str) -> str:
        """The prompt language used for this request ("pt" or "en")."""
        return detect_language(request) if self.language == AUTO else self.language

    def plan(
        self,
        request: str,
        url: str,
        page_elements: Optional[list[str]] = None,
        history: Optional[list[str]] = None,
        known_goals: Optional[set[str]] = None,
        notes: Optional[list[str]] = None,
    ) -> Plan:
        """
        history: what already happened in the run (steps done and failures), for replanning.
        known_goals: ids of the goals already defined in the run (a replan may refer to them).
        notes: the user's notes about this task, from earlier runs of a saved automation.
        """
        self.last_attempts = []
        language = self.language_for(request)
        messages = [
            {"role": "system", "content": system_prompt(language)},
            {"role": "user", "content": user_message(request, url, page_elements, history, language, notes)},
        ]
        tokens_in = tokens_out = 0
        start = time.perf_counter()
        last_error: Optional[PlanError] = None

        for attempt in range(1, self.max_attempts + 1):
            response = self._call(messages)
            usage = getattr(response, "usage", None)
            tokens_in += getattr(usage, "prompt_tokens", 0) or 0
            tokens_out += getattr(usage, "completion_tokens", 0) or 0
            raw = response.choices[0].message.content or ""
            try:
                data = _extract_json(raw, language)
                steps = parse_plan(data, language)
                goals = parse_goals(data, language)
                check_goals(steps, goals, known_goals, language)
                check_values_from_request(steps, [request] + list(notes or []), language)
                if not history and steps:
                    # Only the initial plan covers the whole request.
                    check_request(steps, goals, request, language)
                return Plan(steps=steps, goals=goals, model=self.model, latency_s=round(time.perf_counter() - start, 2),
                            tokens_in=tokens_in, tokens_out=tokens_out, attempts=attempt, raw=raw)
            except PlanError as exc:
                self.last_attempts.append((raw, str(exc)))
                last_error = exc
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": mt("plan.retry", language, error=exc)},
                ]

        raise PlanError(t("planner.gave_up", attempts=self.max_attempts, error=last_error))
