"""Adaptador para o Claude (SDK ``anthropic``)."""

from collections.abc import Sequence
from typing import Any

import anthropic

from cubo.llm.base import MAX_TOOL_ROUNDS, ChatProvider, Exchange, ProviderError, Reply
from cubo.tools.registry import ToolRegistry

MAX_TOKENS = 16000

# Conversa por voz pede respostas rápidas e curtas.
VOICE_EFFORT = "low"

# Os blocos de raciocínio ficam presos ao histórico em que foram gerados. A janela de memória
# descarta as trocas mais antigas, o que muda esse histórico; com "drop_block" a API descarta só
# os blocos afetados em vez de recusar o pedido.
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"
THINKING = {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}

# Se o modelo recusar o pedido por segurança, a API tenta de novo num modelo alternativo.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MODELS_WITH_FALLBACK = frozenset(
    {
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-fable-5-1",
        "claude-fable-5-2",
    }
)


class ClaudeProvider(ChatProvider):
    name = "claude"
    display_name = "Claude"

    def __init__(
        self, *, api_key: str, model: str, client: anthropic.Anthropic | None = None
    ) -> None:
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._model = model

    def reply(
        self,
        *,
        system: str,
        history: Sequence[Exchange],
        user_text: str,
        tools: ToolRegistry,
    ) -> Reply:
        tool_specs = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": dict(tool.parameters),
            }
            for tool in tools
        ]
        previous = self.history_messages(history)
        new_messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._create(system, tool_specs, [*previous, *new_messages])
            if response.stop_reason == "refusal":
                raise ProviderError.refused()
            # O conteúdo volta inteiro para o histórico: os blocos de raciocínio precisam dele.
            new_messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                return Reply(_text_of(response.content), Exchange(self.name, tuple(new_messages)))
            # Todos os resultados vão numa única mensagem, como a API espera.
            results = [
                _tool_result(block, tools) for block in response.content if block.type == "tool_use"
            ]
            new_messages.append({"role": "user", "content": results})

        raise ProviderError.too_many_tool_rounds()

    def list_models(self) -> list[str]:
        try:
            return [model.id for model in self._client.models.list()]
        except anthropic.APIError as error:
            raise self._translate(error) from error

    def _create(
        self, system: str, tool_specs: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> Any:
        options: dict[str, Any] = {"betas": [THINKING_BINDING_BETA]}
        if tool_specs:
            options["tools"] = tool_specs
        if self._model in MODELS_WITH_FALLBACK:
            options["betas"].append(FALLBACK_BETA)
            options["fallbacks"] = "default"
        try:
            return self._client.beta.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                thinking=THINKING,
                output_config={"effort": VOICE_EFFORT},
                cache_control={"type": "ephemeral"},
                **options,
            )
        except anthropic.APIError as error:
            raise self._translate(error) from error

    def _translate(self, error: anthropic.APIError) -> ProviderError:
        if isinstance(error, anthropic.APIStatusError):
            return ProviderError.from_status(self.display_name, self._model, error.status_code)
        if isinstance(error, anthropic.APIConnectionError):
            return ProviderError.unreachable(self.display_name)
        return ProviderError.failed(self.display_name, type(error).__name__)


def _tool_result(block: Any, tools: ToolRegistry) -> dict[str, Any]:
    outcome = tools.run(block.name, block.input)
    return {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": outcome.content,
        "is_error": outcome.is_error,
    }


def _text_of(content: Sequence[Any]) -> str:
    return "".join(block.text for block in content if block.type == "text").strip()
