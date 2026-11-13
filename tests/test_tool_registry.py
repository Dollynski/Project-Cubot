from cubo.tools.registry import Tool, ToolError, ToolOutcome, ToolRegistry


def make_tool(handler):
    return Tool(name="teste", description="", parameters={"type": "object"}, handler=handler)


def test_runs_tool_with_arguments():
    registry = ToolRegistry([make_tool(lambda args: f"olá {args['nome']}")])

    assert registry.run("teste", {"nome": "Cubô"}) == ToolOutcome("olá Cubô")


def test_unknown_tool_is_an_error_result():
    outcome = ToolRegistry().run("sumiu", {})

    assert outcome.is_error
    assert "sumiu" in outcome.content


def test_tool_error_message_goes_back_to_the_model():
    def fail(_args):
        raise ToolError("luz indisponível")

    assert ToolRegistry([make_tool(fail)]).run("teste", {}) == ToolOutcome(
        "luz indisponível", is_error=True
    )


def test_unexpected_exception_does_not_escape():
    def crash(_args):
        raise KeyError("bug")

    outcome = ToolRegistry([make_tool(crash)]).run("teste", {})

    assert outcome.is_error
    assert "bug" not in outcome.content
