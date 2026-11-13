"""Ferramentas e respostas falsas compartilhadas pelos testes dos provedores."""

import httpx2

from cubo.tools.registry import Tool, ToolError, ToolRegistry

REQUEST = httpx2.Request("POST", "https://api.example/v1")


def http_response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=REQUEST)


def home_tools() -> ToolRegistry:
    """Uma ferramenta que funciona e outra que sempre falha."""

    def read(arguments):
        return f"{arguments['dispositivo']}: ligado"

    def broken(_arguments):
        raise ToolError("dispositivo indisponível")

    return ToolRegistry(
        [
            Tool("ler_estado", "Lê o estado.", {"type": "object"}, read),
            Tool("quebrada", "Sempre falha.", {"type": "object"}, broken),
        ]
    )
