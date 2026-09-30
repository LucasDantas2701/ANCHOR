"""
Contrato entre o Executor e quem pergunta ao usuário.

O Executor não sabe se a pergunta aparece no terminal, numa página web
ou num app: ele só monta um ChoiceRequest e recebe um UserChoice.
Para criar outra interface (ex.: o frontend), basta implementar
o protocolo Disambiguator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol


@dataclass
class CandidateView:
    """Um candidato descrito para uma pessoa não-técnica."""
    number: int          # número mostrado na página (1, 2, 3...)
    kind: str            # "Botão", "Link", "Campo de texto"...
    name: str            # texto, rótulo ou pista visual do elemento
    near: str            # texto ao redor, para diferenciar elementos iguais


@dataclass
class ChoiceRequest:
    action: str                      # ação pedida (click, fill...)
    description: str                 # passo em linguagem natural
    reason: Literal["ambiguous", "not_found"]
    candidates: list[CandidateView]
    screenshot: Optional[bytes]      # captura com os números (quando não há janela visível)
    can_point: bool                  # o usuário pode clicar direto na página?


@dataclass
class UserChoice:
    kind: Literal["candidate", "point", "skip"]
    number: Optional[int] = None     # só para kind == "candidate"


class Disambiguator(Protocol):
    def choose(self, request: ChoiceRequest) -> UserChoice:
        """Mostra os candidatos e devolve a escolha do usuário."""
        ...

    def notify(self, message: str) -> None:
        """Mostra uma mensagem curta ao usuário (ex.: 'clique no elemento')."""
        ...
