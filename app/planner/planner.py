"""Planejador: pedido do usuário → lista de passos, usando um LLM."""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Protocol

from openai import BadRequestError

from .plan import PLAN_SCHEMA, Plan, PlanError, parse_plan
from .prompt import SYSTEM, user_message


class Planner(Protocol):
    def plan(
        self,
        request: str,
        url: str,
        page_elements: Optional[list[str]] = None,
        history: Optional[list[str]] = None,
    ) -> Plan: ...


def _extract_json(text: str) -> object:
    """Aceita JSON puro ou dentro de ```json ... ``` (modelos locais às vezes fazem isso)."""
    text = (text or "").strip()
    # Modelos "thinking" às vezes põem o raciocínio na resposta: descarta.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"a resposta não é um JSON válido ({exc.msg})") from exc


class LLMPlanner:
    """
    client: um cliente com a interface do SDK da OpenAI (client.chat.completions.create).
    max_attempts: se o modelo devolver um plano inválido, ele recebe o erro e tenta de novo.
    extra_body: parâmetros extras repassados ao servidor em cada chamada
                (ex.: para desligar o raciocínio de um modelo "thinking").
    """

    def __init__(self, client, model: str, temperature: float = 0.0, max_attempts: int = 2, seed: int = 7,
                 extra_body: Optional[dict] = None):
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
                self._schema_supported = False  # servidor sem suporte a esquema: pede só JSON
        return self.client.chat.completions.create(**kwargs, response_format={"type": "json_object"})

    def plan(
        self,
        request: str,
        url: str,
        page_elements: Optional[list[str]] = None,
        history: Optional[list[str]] = None,
    ) -> Plan:
        """history: o que já aconteceu na execução (passos feitos e falhas), para replanejar."""
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message(request, url, page_elements, history)},
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
                steps = parse_plan(_extract_json(raw))
                return Plan(steps=steps, model=self.model, latency_s=round(time.perf_counter() - start, 2),
                            tokens_in=tokens_in, tokens_out=tokens_out, attempts=attempt, raw=raw)
            except PlanError as exc:
                last_error = exc
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Plano inválido: {exc}. Corrija e responda só com o JSON."},
                ]

        raise PlanError(f"plano inválido depois de {self.max_attempts} tentativas: {last_error}")
