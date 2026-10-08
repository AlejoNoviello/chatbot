"""Tests del loop agéntico con un cliente falso (no llama a la API)."""

from types import SimpleNamespace

import pytest

from chatbot import Agent, AgentError, Config


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def message(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=None)


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.msg.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)

    def get_final_message(self):
        return self.msg


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.calls.append({**params, "messages": list(params["messages"])})
        return FakeStream(self.responses.pop(0))


def test_respuesta_simple():
    client = FakeClient([message([text("¡Hola!")], "end_turn")])
    agent = Agent(Config(), client=client)
    chunks = []
    result = agent.send("hola", on_text=chunks.append)
    assert result.text == "¡Hola!"
    assert chunks == ["¡Hola!"]
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "medium"}


def test_loop_con_herramienta():
    client = FakeClient([
        message([text("Calculo."), tool_use("t1", "calculadora", {"expresion": "2*21"})], "tool_use"),
        message([text("Da 42.")], "end_turn"),
    ])
    agent = Agent(Config(), client=client)
    seen = []
    result = agent.send("¿2*21?", on_tool=lambda *a: seen.append(a))
    assert result.tool_calls == 1
    assert seen == [("calculadora", {"expresion": "2*21"}, "42", False)]
    tool_msg = agent.messages[2]
    assert tool_msg["role"] == "user"
    assert tool_msg["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "42"}
    assert "Da 42." in result.text


def test_rechazo_no_queda_en_historial():
    client = FakeClient([message([], "refusal")])
    agent = Agent(Config(), client=client)
    with pytest.raises(AgentError):
        agent.send("algo")
    assert agent.messages == []


def test_limite_de_iteraciones():
    loop = message([tool_use("t", "calculadora", {"expresion": "1"})], "tool_use")
    client = FakeClient([loop] * 3)
    agent = Agent(Config(max_tool_iterations=3), client=client)
    with pytest.raises(AgentError):
        agent.send("bucle")
    assert agent.messages == []


def test_web_search_opcional():
    client = FakeClient([message([text("ok")], "end_turn")])
    Agent(Config(web_search=True), client=client).send("hola")
    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "web_search" in names
