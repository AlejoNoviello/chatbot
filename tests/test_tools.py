from chatbot import tools


def test_calculadora_basica():
    assert tools.execute("calculadora", {"expresion": "(3 + 4) * 2"}) == ("14", False)


def test_calculadora_funciones_y_constantes():
    content, is_error = tools.execute("calculadora", {"expresion": "sqrt(16) + round(pi, 2)"})
    assert not is_error
    assert float(content) == 4 + 3.14


def test_calculadora_rechaza_codigo_arbitrario():
    content, is_error = tools.execute("calculadora", {"expresion": "__import__('os').system('ls')"})
    assert is_error
    assert "no permitida" in content


def test_calculadora_division_por_cero():
    content, is_error = tools.execute("calculadora", {"expresion": "1/0"})
    assert is_error and "cero" in content


def test_fecha_hora_zona_valida():
    content, is_error = tools.execute("obtener_fecha_hora", {"zona_horaria": "Europe/Madrid"})
    assert not is_error and "Europe/Madrid" in content


def test_fecha_hora_zona_invalida():
    _, is_error = tools.execute("obtener_fecha_hora", {"zona_horaria": "Marte/Base"})
    assert is_error


def test_validacion_de_entrada():
    _, is_error = tools.execute("calculadora", {})
    assert is_error
    _, is_error = tools.execute("calculadora", {"expresion": 5})
    assert is_error
    _, is_error = tools.execute("calculadora", {"expresion": "1", "extra": True})
    assert is_error


def test_tool_desconocida():
    assert tools.execute("no_existe", {})[1] is True


def test_api_tools_es_deterministico():
    names = [t["name"] for t in tools.api_tools()]
    assert names == sorted(names)
    assert all(t["eager_input_streaming"] for t in tools.api_tools())
