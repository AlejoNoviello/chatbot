"""Configuración del chatbot, leída de variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

DEFAULT_SYSTEM_PROMPT = """\
Sos un asistente conversacional útil, claro y amable. Respondés en el idioma \
en el que te escribe el usuario (por defecto, español).

Tenés herramientas disponibles. Usalas cuando aporten un dato que no podés \
saber con certeza (por ejemplo la fecha y hora actual o un cálculo exacto). \
Si ninguna herramienta sirve para lo que te piden, decilo en lugar de adivinar.\
"""


@dataclass(frozen=True)
class Config:
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_tokens: int = 64000
    max_tool_iterations: int = 10
    web_search: bool = False
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_env(cls) -> "Config":
        effort = os.environ.get("CHATBOT_EFFORT", cls.effort).lower()
        if effort not in EFFORT_LEVELS:
            raise ValueError(
                f"CHATBOT_EFFORT inválido: {effort!r}. Usá uno de {EFFORT_LEVELS}."
            )
        return cls(
            model=os.environ.get("CHATBOT_MODEL", cls.model),
            effort=effort,
            web_search=os.environ.get("CHATBOT_WEB_SEARCH", "0") in ("1", "true", "yes"),
        )
