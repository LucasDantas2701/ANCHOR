"""
Model profiles (the llm_profiles.json file at the project root).

Each profile says WHERE the model is and HOW to authenticate, without storing
the key: "api_key_env" is the NAME of the environment variable holding the key.
Two kinds of API:
"openai" (default): the OpenAI API format (OpenAI, or Ollama at /v1).
"ollama": Ollama's native API, which can turn off reasoning
("think": false) and set options such as "num_ctx".
"prompt_language" chooses the planner prompt's language: "pt" (default,
the measured one) or "en".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import OpenAI

from anchor.i18n import t

from .ollama_client import OllamaClient

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "llm_profiles.json"


class ConfigError(RuntimeError):
    pass


@dataclass
class LLMProfile:
    name: str
    model: str
    base_url: Optional[str] = None       # None = the OpenAI API
    api_key_env: Optional[str] = None    # None = no key (e.g. local Ollama)
    temperature: float = 0.0
    timeout_s: float = 180.0
    extra_body: Optional[dict] = None    # extra parameters passed to the server
    api: str = "openai"                  # "openai" or "ollama" (native API)
    think: Optional[bool] = False        # "ollama" API only: reasoning of "thinking" models
    options: Optional[dict] = None       # "ollama" API only: e.g. {"num_ctx": 4096}
    prompt_language: str = "pt"          # planner prompt language: "pt" (measured) or "en"

    def planner(self, on_progress=None, prompt_language: Optional[str] = None):
        """A planner ready for this profile (on_progress: see OllamaClient; prompt_language overrides the profile's)."""
        from .planner import LLMPlanner
        return LLMPlanner(self.client(on_progress), self.model, temperature=self.temperature,
                          extra_body=self.extra_body, language=prompt_language or self.prompt_language)

    def api_key(self) -> str:
        if not self.api_key_env:
            return "no-key"  # Ollama ignores the key, but the SDK requires one
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ConfigError(t("config.needs_key", profile=self.name, env=self.api_key_env))
        return key

    def client(self, on_progress=None):
        if not self.model or self.model.startswith(("COLOQUE", "PUT_")):
            raise ConfigError(t("config.no_model", profile=self.name))
        if self.api == "ollama":
            return OllamaClient(self.base_url, self.timeout_s, think=self.think, options=self.options,
                                on_progress=on_progress)
        if self.api != "openai":
            raise ConfigError(t("config.bad_api", profile=self.name, api=self.api))
        # max_retries=0: no hidden SDK retries; a timeout shows up right away.
        return OpenAI(api_key=self.api_key(), base_url=self.base_url, timeout=self.timeout_s, max_retries=0)


def load_profiles(path: Path | str = DEFAULT_FILE) -> dict[str, LLMProfile]:
    path = Path(path)
    if not path.exists():
        raise ConfigError(t("config.no_file", path=path))
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["name"]: LLMProfile(**p) for p in data["profiles"]}


# Old profile names, still accepted.
PROFILE_ALIASES = {"ollama-pequeno": "ollama-small", "ollama-medio": "ollama-medium"}


def get_profile(name: str, path: Path | str = DEFAULT_FILE) -> LLMProfile:
    profiles = load_profiles(path)
    if name not in profiles and PROFILE_ALIASES.get(name) in profiles:
        name = PROFILE_ALIASES[name]
    if name not in profiles:
        raise ConfigError(t("config.unknown_profile", profile=name, available=", ".join(profiles)))
    return profiles[name]
