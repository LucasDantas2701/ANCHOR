"""
Perfis de modelo (arquivo llm_profiles.json na raiz do projeto).

Cada perfil diz ONDE está o modelo e COMO autenticar, sem guardar a
chave: "api_key_env" é o NOME da variável de ambiente com a chave.
Dois tipos de API:
    "openai" (padrão): formato da API da OpenAI (OpenAI, ou o Ollama em /v1).
    "ollama": API nativa do Ollama, que permite desligar o raciocínio
              ("think": false) e ajustar opções como "num_ctx".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .ollama_client import OllamaClient

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "llm_profiles.json"


class ConfigError(RuntimeError):
    pass


@dataclass
class LLMProfile:
    name: str
    model: str
    base_url: Optional[str] = None       # None = API da OpenAI
    api_key_env: Optional[str] = None    # None = sem chave (ex.: Ollama local)
    temperature: float = 0.0
    timeout_s: float = 180.0
    extra_body: Optional[dict] = None    # parâmetros extras repassados ao servidor
    api: str = "openai"                  # "openai" ou "ollama" (API nativa)
    think: Optional[bool] = False        # só na API "ollama": raciocínio dos modelos "thinking"
    options: Optional[dict] = None       # só na API "ollama": ex. {"num_ctx": 4096}

    def planner(self, on_progress=None):
        """Planejador pronto para este perfil (on_progress: ver OllamaClient)."""
        from .planner import LLMPlanner
        return LLMPlanner(self.client(on_progress), self.model, temperature=self.temperature,
                          extra_body=self.extra_body)

    def api_key(self) -> str:
        if not self.api_key_env:
            return "sem-chave"  # o Ollama ignora a chave, mas o SDK exige uma
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ConfigError(
                f'O perfil "{self.name}" precisa da variável de ambiente {self.api_key_env}.\n'
                f'No Windows: setx {self.api_key_env} "sua-chave" (e abra um terminal novo).'
            )
        return key

    def client(self, on_progress=None):
        if not self.model or self.model.startswith("COLOQUE"):
            raise ConfigError(f'Defina o campo "model" do perfil "{self.name}" em llm_profiles.json.')
        if self.api == "ollama":
            return OllamaClient(self.base_url, self.timeout_s, think=self.think, options=self.options,
                                on_progress=on_progress)
        if self.api != "openai":
            raise ConfigError(f'Perfil "{self.name}": "api" deve ser "openai" ou "ollama", não "{self.api}".')
        # max_retries=0: sem novas tentativas escondidas do SDK; um tempo esgotado aparece na hora.
        return OpenAI(api_key=self.api_key(), base_url=self.base_url, timeout=self.timeout_s, max_retries=0)


def load_profiles(path: Path | str = DEFAULT_FILE) -> dict[str, LLMProfile]:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Arquivo de perfis não encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["name"]: LLMProfile(**p) for p in data["profiles"]}


def get_profile(name: str, path: Path | str = DEFAULT_FILE) -> LLMProfile:
    profiles = load_profiles(path)
    if name not in profiles:
        raise ConfigError(f'Perfil "{name}" não existe. Disponíveis: {", ".join(profiles)}')
    return profiles[name]
