# Chatbot agente de IA

Chatbot de terminal construido sobre la [API de Claude](https://platform.claude.com/docs) que funciona como **agente**: además de conversar, decide cuándo usar herramientas (tools), las ejecuta y sigue razonando con los resultados hasta responder.

## Características

- Conversación multi-turno con respuestas en **streaming**.
- **Loop agéntico** propio: Claude pide una herramienta → se ejecuta localmente → se le devuelve el resultado → repite hasta terminar (con límite de iteraciones).
- Herramientas incluidas:
  - `obtener_fecha_hora`: fecha y hora actual en cualquier zona horaria.
  - `calculadora`: evaluación aritmética exacta y segura (sin `eval`).
  - `web_search` (opcional): búsqueda web ejecutada por los servidores de Anthropic.
- Validación de los argumentos de cada herramienta antes de ejecutarla.
- **Prompt caching** automático del historial para bajar costo y latencia.
- **Fallback del lado del servidor** (`fallbacks: "default"`): si los clasificadores de seguridad rechazan un pedido, la API lo reintenta en otro modelo automáticamente.
- El historial queda consistente ante errores, rechazos o Ctrl+C.

## Instalación

Requiere Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuración

Copiá `.env.example` y exportá las variables (o definilas en tu shell):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

| Variable | Default | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Clave de la API (obligatoria). |
| `CHATBOT_MODEL` | `claude-opus-5-5` | Modelo de Claude a usar. |
| `CHATBOT_EFFORT` | `medium` | Profundidad de razonamiento: `low`, `medium`, `high`, `xhigh`, `max`. |
| `CHATBOT_WEB_SEARCH` | `0` | `1` para habilitar la búsqueda web. |

## Uso

```bash
chatbot            # o: python -m chatbot
```

```
vos> ¿Qué hora es en Madrid y cuánto es 17% de 2350?
bot> 
  ↳ obtener_fecha_hora({"zona_horaria": "Europe/Madrid"}) [ok] → 2026-10-08 21:15:03 ...
  ↳ calculadora({"expresion": "2350 * 0.17"}) [ok] → 399.5
En Madrid son las 21:15 y el 17% de 2350 es 399,5.
```

Comandos: `/reset` (borra el historial), `/ayuda`, `/salir`.

## Estructura

```
chatbot/
  config.py   # Configuración y system prompt
  tools.py    # Registro de herramientas, validación y ejecución
  agent.py    # Loop agéntico (streaming + tool use)
  cli.py      # Interfaz de terminal
tests/        # Tests con un cliente falso (no consumen la API)
```

## Agregar una herramienta

En `chatbot/tools.py`:

```python
@tool(
    name="clima",
    description="Devuelve el clima actual de una ciudad. Usala cuando pregunten por el clima.",
    input_schema={
        "type": "object",
        "properties": {"ciudad": {"type": "string", "description": "Nombre de la ciudad"}},
        "required": ["ciudad"],
        "additionalProperties": False,
    },
)
def clima(ciudad: str) -> str:
    ...  # llamar a tu API de clima
    return "18°C, nublado"
```

Las herramientas devuelven un string; para errores esperados lanzá `ToolError("mensaje")` y Claude lo recibirá como error para corregirse.

## Tests

```bash
pytest
```

## Próximos pasos posibles

- Memoria persistente entre sesiones (guardar el historial en disco/base de datos).
- Interfaz web (FastAPI + frontend) o integración con WhatsApp/Telegram.
- Más herramientas: consultas a una base de datos, RAG sobre documentos propios, APIs internas.
- Compactación del contexto para conversaciones muy largas.
