"""Interfaz de línea de comandos del chatbot."""

from __future__ import annotations

import json
import sys

import anthropic

from .agent import Agent, AgentError
from .config import Config

HELP = """\
Comandos:
  /reset   Borra el historial de la conversación
  /ayuda   Muestra esta ayuda
  /salir   Termina la sesión (también Ctrl+D)
"""

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _print_text(chunk: str) -> None:
    print(chunk, end="", flush=True)


def _print_tool(name: str, args: object, result: str, is_error: bool) -> None:
    status = "error" if is_error else "ok"
    preview = result if len(result) <= 200 else result[:200] + "…"
    print(
        f"\n{DIM}  ↳ {name}({json.dumps(args, ensure_ascii=False)}) [{status}] → {preview}{RESET}",
        flush=True,
    )


def main() -> int:
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Error de configuración: {e}", file=sys.stderr)
        return 2

    agent = Agent(config)
    extras = " + búsqueda web" if config.web_search else ""
    print(f"{BOLD}Chatbot agente{RESET} — modelo {config.model} (effort {config.effort}){extras}")
    print("Escribí /ayuda para ver los comandos.\n")

    while True:
        try:
            user_text = input(f"{BOLD}vos>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_text:
            continue
        if user_text in ("/salir", "/exit", "/quit"):
            return 0
        if user_text == "/ayuda":
            print(HELP)
            continue
        if user_text == "/reset":
            agent.reset()
            print("Historial borrado.\n")
            continue

        print(f"{BOLD}bot>{RESET} ", end="", flush=True)
        try:
            agent.send(user_text, on_text=_print_text, on_tool=_print_tool)
            print("\n")
        except KeyboardInterrupt:
            print("\n[interrumpido]\n")
        except AgentError as e:
            print(f"\n[{e}]\n")
        except (anthropic.AuthenticationError, TypeError) as e:
            # El SDK lanza TypeError si no encuentra ninguna credencial.
            if isinstance(e, TypeError) and "authentication" not in str(e):
                raise
            print("\n[Error de autenticación: definí ANTHROPIC_API_KEY (ver .env.example)]\n")
            return 1
        except anthropic.RateLimitError:
            print("\n[Límite de uso alcanzado; esperá un momento y reintentá]\n")
        except anthropic.APIStatusError as e:
            print(f"\n[Error de la API ({e.status_code}): {e.message}]\n")
        except anthropic.APIConnectionError:
            print("\n[Error de conexión; revisá tu red]\n")


if __name__ == "__main__":
    sys.exit(main())
