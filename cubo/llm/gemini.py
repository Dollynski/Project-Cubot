"""Adaptador para o Gemini (SDK ``google-genai``)."""

from collections.abc import Sequence
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types

from cubo.llm.base import MAX_TOOL_ROUNDS, ChatProvider, Exchange, ProviderError, Reply
from cubo.tools.registry import ToolRegistry


class GeminiProvider(ChatProvider):
    name = "gemini"
    display_name = "Gemini"

    def __init__(self, *, api_key: str, model: str, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(api_key=api_key)
        self._model = model

    def reply(
        self,
        *,
        system: str,
        history: Sequence[Exchange],
        user_text: str,
        tools: ToolRegistry,
    ) -> Reply:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=_declarations(tools) or None,
            # O Cubô executa as ferramentas pelo próprio registro, igual nos outros provedores.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        previous = self.history_messages(history)
        new_contents = [types.Content(role="user", parts=[types.Part(text=user_text)])]

        for _ in range(MAX_TOOL_ROUNDS):
            response = self._generate([*previous, *new_contents], config)
            content = response.candidates[0].content if response.candidates else None
            if content is None:
                # Sem candidato: o pedido foi bloqueado pelos filtros de segurança.
                raise ProviderError.refused()
            new_contents.append(content)
            calls = response.function_calls or []
            if not calls:
                return Reply(_text_of(content), Exchange(self.name, tuple(new_contents)))
            # O Gemini 3 exige uma resposta por chamada, com o mesmo id e nome.
            responses = [_function_response(call, tools) for call in calls]
            new_contents.append(types.Content(role="user", parts=responses))

        raise ProviderError.too_many_tool_rounds()

    def list_models(self) -> list[str]:
        try:
            models = list(self._client.models.list())
        except (errors.APIError, httpx2.TransportError) as error:
            raise self._translate(error) from error
        return [
            model.name.removeprefix("models/")
            for model in models
            if model.name and "generateContent" in (model.supported_actions or [])
        ]

    def _generate(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            return self._client.models.generate_content(
                model=self._model, contents=contents, config=config
            )
        except (errors.APIError, httpx2.TransportError) as error:
            raise self._translate(error) from error

    def _translate(self, error: Exception) -> ProviderError:
        if isinstance(error, httpx2.TransportError):
            return ProviderError.unreachable(self.display_name)
        if isinstance(error, errors.APIError):
            # Chave inválida volta como 400, não 401.
            if error.code == 400 and "API key" in (error.message or ""):
                return ProviderError.invalid_key(self.display_name)
            return ProviderError.from_status(self.display_name, self._model, error.code)
        return ProviderError.failed(self.display_name, type(error).__name__)


def _declarations(tools: ToolRegistry) -> list[types.Tool]:
    if not len(tools):
        return []
    declarations = [
        types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters_json_schema=dict(tool.parameters),
        )
        for tool in tools
    ]
    return [types.Tool(function_declarations=declarations)]


def _function_response(call: types.FunctionCall, tools: ToolRegistry) -> types.Part:
    outcome = tools.run(call.name or "", call.args or {})
    result: dict[str, Any] = {"error" if outcome.is_error else "output": outcome.content}
    return types.Part(
        function_response=types.FunctionResponse(id=call.id, name=call.name, response=result)
    )


def _text_of(content: types.Content) -> str:
    return "".join(
        part.text for part in content.parts or [] if part.text and not part.thought
    ).strip()
