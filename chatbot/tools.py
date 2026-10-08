"""Herramientas (tools) que el agente puede invocar.

Para agregar una herramienta nueva: escribí una función que reciba los
argumentos como keywords y devuelva un string, y registrala con `@tool(...)`
indicando su descripción y el JSON Schema de su entrada.
"""

from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ToolError(Exception):
    """Error esperado de una herramienta; se le devuelve a Claude como is_error."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    func: Callable[..., str]

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            # Respondemos en streaming: los argumentos llegan a medida que se
            # generan, así que validamos la entrada nosotros (ver validate_input).
            "eager_input_streaming": True,
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, input_schema: dict[str, Any]):
    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        REGISTRY[name] = Tool(name, description, input_schema, func)
        return func

    return decorator


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def validate_input(schema: dict[str, Any], args: Any) -> str | None:
    """Validación mínima de un objeto contra un JSON Schema plano.

    Devuelve un mensaje de error, o None si la entrada es válida.
    """
    if not isinstance(args, dict):
        return "la entrada debe ser un objeto JSON"
    properties = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            return f"falta el parámetro requerido {key!r}"
    for key, value in args.items():
        prop = properties.get(key)
        if prop is None:
            if schema.get("additionalProperties") is False:
                return f"parámetro desconocido {key!r}"
            continue
        expected = _JSON_TYPES.get(prop.get("type", ""))
        # bool es subclase de int en Python; no lo aceptamos como número.
        if expected and (not isinstance(value, expected) or (
            isinstance(value, bool) and prop["type"] != "boolean"
        )):
            return f"{key!r} debe ser de tipo {prop['type']}"
        if "enum" in prop and value not in prop["enum"]:
            return f"{key!r} debe ser uno de {prop['enum']}"
    return None


def execute(name: str, args: Any) -> tuple[str, bool]:
    """Ejecuta una herramienta. Devuelve (contenido, es_error)."""
    t = REGISTRY.get(name)
    if t is None:
        return f"Herramienta desconocida: {name}", True
    problem = validate_input(t.input_schema, args)
    if problem:
        return json.dumps({"INVALID_INPUT": problem, "input": args}, ensure_ascii=False), True
    try:
        return t.func(**args), False
    except ToolError as e:
        return f"Error: {e}", True
    except Exception as e:  # noqa: BLE001 - nunca romper el loop por una tool
        return f"Error inesperado en {name}: {type(e).__name__}: {e}", True


def api_tools() -> list[dict[str, Any]]:
    # Orden determinístico: mantiene estable el prefijo para el prompt cache.
    return [REGISTRY[name].to_api() for name in sorted(REGISTRY)]


# --------------------------------------------------------------------------
# Herramientas incluidas
# --------------------------------------------------------------------------


@tool(
    name="obtener_fecha_hora",
    description=(
        "Devuelve la fecha y hora actual en una zona horaria IANA "
        "(por ejemplo 'America/Argentina/Buenos_Aires' o 'Europe/Madrid'). "
        "Usala siempre que necesites saber la fecha u hora actual."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "zona_horaria": {
                "type": "string",
                "description": "Zona horaria IANA. Por defecto 'America/Argentina/Buenos_Aires'.",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
)
def obtener_fecha_hora(zona_horaria: str = "America/Argentina/Buenos_Aires") -> str:
    try:
        tz = ZoneInfo(zona_horaria)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(f"zona horaria desconocida: {zona_horaria!r}")
    now = datetime.now(tz)
    return now.strftime(f"%Y-%m-%d %H:%M:%S ({zona_horaria}, %A)")


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ToolError("exponente demasiado grande")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
    ):
        return _FUNCS[node.func.id](*(_eval_node(a) for a in node.args))
    raise ToolError("expresión no permitida")


@tool(
    name="calculadora",
    description=(
        "Evalúa una expresión aritmética de forma exacta. Soporta + - * / // % **, "
        "paréntesis, las constantes pi y e, y las funciones sqrt, abs, round, log, "
        "log10, sin, cos y tan. Usala para cualquier cálculo no trivial."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "expresion": {
                "type": "string",
                "description": "Expresión a evaluar, por ejemplo '(3 + 4) * sqrt(2)'.",
            }
        },
        "required": ["expresion"],
        "additionalProperties": False,
    },
)
def calculadora(expresion: str) -> str:
    if len(expresion) > 500:
        raise ToolError("expresión demasiado larga")
    try:
        tree = ast.parse(expresion, mode="eval")
    except SyntaxError:
        raise ToolError(f"sintaxis inválida: {expresion!r}")
    try:
        result = _eval_node(tree)
    except ZeroDivisionError:
        raise ToolError("división por cero")
    except (OverflowError, ValueError) as e:
        raise ToolError(str(e))
    return str(result)
