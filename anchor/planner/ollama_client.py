"""
Client for Ollama's native API (/api/chat), with a chat-completions interface
(client.chat.completions.create) the planner calls.

Why the native API: it can turn off the reasoning of "thinking" models
("think": false) and set options such as the context size ("num_ctx").
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Callable, Optional

import requests

from anchor.i18n import t


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_s: float = 180.0,
        think: Optional[bool] = False,
        options: Optional[dict] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ):
        """
        on_progress(phase, tokens): called for each chunk of the answer, with
        phase "thinking" or "writing". With it, the answer is streamed.
        """
        base = (base_url or "http://localhost:11434").rstrip("/")
        if base.endswith("/v1"):  # accepts an address ending in /v1 by mistake
            base = base[:-3]
        self.base = base
        self.url = base + "/api/chat"
        self.timeout_s = timeout_s
        self.think = think
        self.options = options or {}
        self.on_progress = on_progress
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def environment(self, model: str) -> dict:
        """
        The Ollama version and the model's identifier (digest) and date, so a measurement records
        exactly what it ran on: with the same model files, an Ollama update changed answers.
        """
        env = {"server": "ollama", "server_version": None, "model": model, "model_digest": None,
               "model_modified": None}
        try:
            env["server_version"] = requests.get(self.base + "/api/version", timeout=5).json().get("version")
            for m in requests.get(self.base + "/api/tags", timeout=5).json().get("models", []):
                if m.get("name") == model or m.get("model") == model:
                    env["model_digest"], env["model_modified"] = m.get("digest"), m.get("modified_at")
        except Exception:
            pass
        return env

    def _create(self, model, messages, temperature=None, seed=None,
                response_format=None, extra_body=None, **_ignored):
        streaming = self.on_progress is not None
        body = {"model": model, "messages": messages, "stream": streaming}
        if self.think is not None:
            body["think"] = self.think

        options = dict(self.options)
        if temperature is not None:
            options.setdefault("temperature", temperature)
        if seed is not None:
            options.setdefault("seed", seed)
        if options:
            body["options"] = options

        kind = (response_format or {}).get("type")
        if kind == "json_schema":
            body["format"] = response_format["json_schema"]["schema"]
        elif kind == "json_object":
            body["format"] = "json"

        if extra_body:
            body.update(extra_body)

        try:
            response = requests.post(self.url, json=body, timeout=self.timeout_s, stream=streaming)
        except requests.ConnectionError as exc:
            raise OllamaError(t("ollama.unreachable", url=self.url)) from exc
        except requests.Timeout as exc:
            raise OllamaError(t("ollama.timeout", seconds=f"{self.timeout_s:.0f}")) from exc

        if response.status_code == 404:
            raise OllamaError(t("ollama.no_model", model=model))
        if response.status_code >= 400:
            raise OllamaError(t("ollama.http_error", status=response.status_code, text=response.text[:200]))

        data = self._read_stream(response) if streaming else response.json()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=data.get("message", {}).get("content", "")))],
            usage=SimpleNamespace(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
            ),
            load_s=(data.get("load_duration") or 0) / 1e9,
        )

    def _read_stream(self, response) -> dict:
        """Joins the chunks of the answer, reporting progress on each one."""
        content, tokens, last = [], 0, {}
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                message = chunk.get("message", {})
                if message.get("thinking"):
                    tokens += 1
                    self.on_progress("thinking", tokens)
                if message.get("content"):
                    content.append(message["content"])
                    tokens += 1
                    self.on_progress("writing", tokens)
                if chunk.get("done"):
                    last = chunk
                    break
        except requests.RequestException as exc:
            raise OllamaError(t("ollama.dropped", error=exc)) from exc
        return {**last, "message": {"content": "".join(content)}}
