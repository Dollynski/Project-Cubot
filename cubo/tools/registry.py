"""Registro de ferramentas, descritas uma vez em JSON Schema e usadas por qualquer provedor."""

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ToolHandler = Callable[[Mapping[str, Any]], str]


class ToolError(Exception):
    """Falha esperada de uma ferramenta. A mensagem é devolvida para a IA explicar ao usuário."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: Mapping[str, Any]  # JSON Schema de um objeto
    handler: ToolHandler


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    is_error: bool = False


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def run(self, name: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        """Executa a ferramenta. Nunca levanta exceção: falhas viram um resultado de erro."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutcome(f"Ferramenta desconhecida: {name}", is_error=True)
        try:
            return ToolOutcome(tool.handler(arguments))
        except ToolError as error:
            return ToolOutcome(str(error), is_error=True)
        except Exception:
            logger.exception("Erro inesperado na ferramenta %s", name)
            return ToolOutcome("Erro inesperado ao executar a ferramenta.", is_error=True)
