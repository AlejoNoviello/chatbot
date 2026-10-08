"""Loop agéntico: conversa con Claude y ejecuta las herramientas que pida."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from . import tools
from .config import Config

# Modelos que aceptan el fallback del lado del servidor (`fallbacks: "default"`):
# si los clasificadores de seguridad rechazan un pedido, la API lo reintenta
# automáticamente en el modelo recomendado para esa categoría.
_FALLBACK_MODELS = ("claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

TextCallback = Callable[[str], None]
ToolCallback = Callable[[str, Any, str, bool], None]


class AgentError(Exception):
    """Un turno no pudo completarse; el historial queda como antes del turno."""


@dataclass
class TurnResult:
    text: str
    stop_reason: str | None
    tool_calls: int = 0


@dataclass
class Agent:
    config: Config = field(default_factory=Config)
    client: Any = None
    messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = anthropic.Anthropic()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.messages.clear()

    def _request_params(self) -> dict[str, Any]:
        api_tools: list[dict[str, Any]] = tools.api_tools()
        if self.config.web_search:
            api_tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 5})
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": self.config.system_prompt,
            "tools": api_tools,
            "messages": self.messages,
            "output_config": {"effort": self.config.effort},
            # Cachea automáticamente el prefijo (system + tools + historial).
            "cache_control": {"type": "ephemeral"},
        }
        if self.config.model.startswith(_FALLBACK_MODELS):
            params["betas"] = [_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def _stream_once(self, on_text: TextCallback | None) -> Any:
        """Una llamada a la API en streaming; devuelve el mensaje final."""
        json_retries = 0
        while True:
            try:
                with self.client.beta.messages.stream(**self._request_params()) as stream:
                    for event in stream:
                        if event.type == "text" and on_text:
                            on_text(event.text)
                    return stream.get_final_message()
            except ValueError:
                # JSON de entrada de una tool que el SDK no pudo parsear
                # (eager_input_streaming). Reintentamos el turno, acotado.
                json_retries += 1
                if json_retries > 2:
                    raise AgentError("Claude generó argumentos de herramienta inválidos.")

    # ------------------------------------------------------------------
    def send(
        self,
        user_text: str,
        on_text: TextCallback | None = None,
        on_tool: ToolCallback | None = None,
    ) -> TurnResult:
        """Envía un mensaje del usuario y corre el loop hasta que Claude termine."""
        checkpoint = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        try:
            return self._run_loop(on_text, on_tool)
        except BaseException:
            # Si el turno falla (error de API, Ctrl+C, ...) volvemos al estado
            # anterior para que la conversación siga siendo válida.
            del self.messages[checkpoint:]
            raise

    def _run_loop(self, on_text: TextCallback | None, on_tool: ToolCallback | None) -> TurnResult:
        texts: list[str] = []
        tool_calls = 0
        for _ in range(self.config.max_tool_iterations):
            response = self._stream_once(on_text)
            texts.extend(b.text for b in response.content if b.type == "text")

            if response.stop_reason == "refusal":
                # No guardamos un turno rechazado en el historial.
                raise _Refusal(response)

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "pause_turn":
                # Una tool del servidor (p.ej. web_search) pausó el turno: continuar.
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return TurnResult("".join(texts), response.stop_reason, tool_calls)

            if response.stop_reason == "max_tokens":
                raise AgentError("La respuesta se cortó por max_tokens en medio de una herramienta.")

            results = []
            for block in tool_uses:
                content, is_error = tools.execute(block.name, block.input)
                tool_calls += 1
                if on_tool:
                    on_tool(block.name, block.input, content, is_error)
                result: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
                if is_error:
                    result["is_error"] = True
                results.append(result)
            # Todos los resultados van juntos en un único mensaje de usuario.
            self.messages.append({"role": "user", "content": results})

        raise AgentError(
            f"Se alcanzó el límite de {self.config.max_tool_iterations} iteraciones de herramientas."
        )


class _Refusal(AgentError):
    def __init__(self, response: Any) -> None:
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        super().__init__(
            "Claude no puede ayudar con este pedido"
            + (f" (categoría: {category})." if category else ".")
        )
