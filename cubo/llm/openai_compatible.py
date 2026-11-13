"""Adaptador para a API de chat da OpenAI, que também atende o Ollama."""

import json
from collections.abc import Sequence
from typing import Any

import openai

from cubo.llm.base import MAX_TOOL_ROUNDS, ChatProvider, Exchange, ProviderError, Reply
from cubo.tools.registry import ToolRegistry


class OpenAICompatibleProvider(ChatProvider):
    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        client: openai.OpenAI | None = None,
    ) -> None:
        self.name = name
        self.display_name = display_name
        self._client = client or openai.OpenAI(api_key=api_key, base_url=base_url)
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
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                },
            }
            for tool in tools
        ]
        previous = [{"role": "system", "content": system}, *self.history_messages(history)]
        new_messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

        for _ in range(MAX_TOOL_ROUNDS):
            message = self._complete([*previous, *new_messages], tool_specs)
            if message.refusal:
                raise ProviderError.refused()
            calls = [call for call in message.tool_calls or [] if call.type == "function"]
            new_messages.append(_assistant_message(message.content, calls))
            if not calls:
                text = (message.content or "").strip()
                return Reply(text, Exchange(self.name, tuple(new_messages)))
            new_messages.extend(_tool_message(call, tools) for call in calls)

        raise ProviderError.too_many_tool_rounds()

    def list_models(self) -> list[str]:
        try:
            return [model.id for model in self._client.models.list()]
        except openai.APIError as error:
            raise self._translate(error) from error

    def _complete(self, messages: list[dict[str, Any]], tool_specs: list[dict[str, Any]]) -> Any:
        options = {"tools": tool_specs} if tool_specs else {}
        try:
            response = self._client.chat.completions.create(
                model=self._model, messages=messages, **options
            )
        except openai.APIError as error:
            raise self._translate(error) from error
        return response.choices[0].message

    def _translate(self, error: openai.APIError) -> ProviderError:
        if isinstance(error, openai.APIStatusError):
            return ProviderError.from_status(self.display_name, self._model, error.status_code)
        if isinstance(error, openai.APIConnectionError):
            return ProviderError.unreachable(self.display_name)
        return ProviderError.failed(self.display_name, type(error).__name__)


def _assistant_message(content: str | None, calls: list[Any]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content or ""}
    if calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in calls
        ]
    return message


def _tool_message(call: Any, tools: ToolRegistry) -> dict[str, Any]:
    try:
        arguments = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        arguments = None
    if isinstance(arguments, dict):
        outcome = tools.run(call.function.name, arguments)
        content = f"Erro: {outcome.content}" if outcome.is_error else outcome.content
    else:
        content = "Erro: os argumentos da ferramenta não são um objeto JSON válido."
    return {"role": "tool", "tool_call_id": call.id, "content": content}
