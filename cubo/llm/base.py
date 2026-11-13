"""Contrato comum dos provedores de IA."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cubo.tools.registry import ToolRegistry

# Limite de idas e voltas com ferramentas num mesmo pedido, para um loop nunca prender o Cubô.
MAX_TOOL_ROUNDS = 5


@dataclass(frozen=True)
class Exchange:
    """Uma troca completa, do pedido do usuário até a resposta final.

    As mensagens ficam no formato nativo do provedor que as gerou, porque cada SDK precisa
    receber de volta exatamente o que devolveu (ids de ferramentas, blocos de raciocínio...).
    """

    provider: str
    messages: tuple[Any, ...]


@dataclass(frozen=True)
class Usage:
    """Tokens gastos num pedido, somando todas as idas e voltas com a IA."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True)
class Reply:
    text: str
    exchange: Exchange
    usage: Usage = Usage()


class ProviderError(Exception):
    """Falha ao usar o provedor, com uma mensagem que pode ser falada ao usuário."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message

    # As mensagens não usam artigo antes do nome ("o Gemini", "a OpenAI") para servirem a todos.

    @classmethod
    def invalid_key(cls, provider: str) -> "ProviderError":
        return cls(f"{provider} recusou a chave de API. Confira a chave configurada.")

    @classmethod
    def model_not_found(cls, provider: str, model: str) -> "ProviderError":
        return cls(f"{provider} não encontrou o modelo {model}. Confira o modelo configurado.")

    @classmethod
    def rate_limited(cls, provider: str) -> "ProviderError":
        return cls(f"{provider} está limitando os pedidos agora. Tente de novo em instantes.")

    @classmethod
    def unreachable(cls, provider: str) -> "ProviderError":
        return cls(f"Não consegui me conectar ao serviço {provider}. Confira a conexão.")

    @classmethod
    def failed(cls, provider: str, detail: str) -> "ProviderError":
        return cls(f"{provider} respondeu com um erro: {detail}.")

    @classmethod
    def from_status(cls, provider: str, model: str, status: int) -> "ProviderError":
        """Traduz o status HTTP de uma resposta de erro do provedor."""
        if status in (401, 403):
            return cls.invalid_key(provider)
        if status == 404:
            return cls.model_not_found(provider, model)
        if status == 429:
            return cls.rate_limited(provider)
        return cls.failed(provider, f"HTTP {status}")

    @classmethod
    def limit_reached(cls, period: str) -> "ProviderError":
        return cls(
            f"Atingi o limite de chamadas à IA por {period}. Dá para ajustar esse limite no painel."
        )

    @classmethod
    def refused(cls) -> "ProviderError":
        return cls("Desculpe, não posso ajudar com isso.")

    @classmethod
    def too_many_tool_rounds(cls) -> "ProviderError":
        return cls("Desculpe, não consegui concluir esse pedido.")


class ChatProvider(ABC):
    name: str  # identificador do provedor, igual ao da configuração
    display_name: str  # nome falado nas mensagens de erro

    @abstractmethod
    def reply(
        self,
        *,
        system: str,
        history: Sequence[Exchange],
        user_text: str,
        tools: ToolRegistry,
    ) -> Reply:
        """Responde ao pedido, executando as ferramentas que a IA chamar.

        Levanta ``ProviderError`` em qualquer falha do provedor.
        """

    @abstractmethod
    def list_models(self) -> list[str]:
        """Modelos disponíveis para a credencial configurada."""

    def history_messages(self, history: Sequence[Exchange]) -> list[Any]:
        """Mensagens das trocas anteriores geradas por este provedor, em ordem."""
        return [
            message
            for exchange in history
            if exchange.provider == self.name
            for message in exchange.messages
        ]
