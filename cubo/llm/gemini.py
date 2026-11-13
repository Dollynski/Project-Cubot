"""Adaptador para o Gemini (SDK ``google-genai``)."""

from collections.abc import Callable, Iterable, Sequence
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types

from cubo.llm.base import MAX_TOOL_ROUNDS, ChatProvider, Exchange, ProviderError, Reply, Usage
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
        on_text: Callable[[str], None] | None = None,
    ) -> Reply:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=_declarations(tools) or None,
            # O Cubô executa as ferramentas pelo próprio registro, igual nos outros provedores.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        previous = self.history_messages(history)
        new_contents = [types.Content(role="user", parts=[types.Part(text=user_text)])]

        usage = Usage()
        for _ in range(MAX_TOOL_ROUNDS):
            response = self._generate([*previous, *new_contents], config, on_text)
            usage += _usage_of(response)
            content = response.candidates[0].content if response.candidates else None
            if content is None:
                # Sem candidato: o pedido foi bloqueado pelos filtros de segurança.
                raise ProviderError.refused()
            new_contents.append(content)
            calls = response.function_calls or []
            if not calls:
                return Reply(_text_of(content), Exchange(self.name, tuple(new_contents)), usage)
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
        self,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
        on_text: Callable[[str], None] | None,
    ) -> types.GenerateContentResponse:
        try:
            if on_text is None:
                return self._client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
            chunks = self._client.models.generate_content_stream(
                model=self._model, contents=contents, config=config
            )
            return _merge_stream(chunks, on_text)
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


def _merge_stream(
    chunks: Iterable[types.GenerateContentResponse], on_text: Callable[[str], None]
) -> types.GenerateContentResponse:
    """Junta os pedaços do streaming numa resposta igual à da chamada sem streaming."""
    parts: list[types.Part] = []
    metadata = None
    for chunk in chunks:
        metadata = chunk.usage_metadata or metadata
        content = chunk.candidates[0].content if chunk.candidates else None
        for part in (content.parts if content else None) or []:
            if part.text and not part.thought:
                on_text(part.text)
            _append_part(parts, part)
    if not parts:
        # Nada veio: o pedido foi bloqueado pelos filtros de segurança.
        return types.GenerateContentResponse(candidates=[], usage_metadata=metadata)
    content = types.Content(role="model", parts=parts)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=content)], usage_metadata=metadata
    )


def _append_part(parts: list[types.Part], part: types.Part) -> None:
    """Soma textos seguidos do mesmo tipo; chamadas de função ficam como vieram.

    A assinatura do raciocínio (``thought_signature``) vai junto com o texto que a recebe, pois
    o Gemini 3 exige que ela volte no histórico.
    """
    previous = parts[-1] if parts else None
    same_kind = (
        previous is not None
        and _is_text(previous)
        and _is_text(part)
        and bool(previous.thought) == bool(part.thought)
    )
    if not same_kind:
        parts.append(part)
        return
    parts[-1] = previous.model_copy(
        update={
            "text": (previous.text or "") + (part.text or ""),
            "thought_signature": part.thought_signature or previous.thought_signature,
        }
    )


def _is_text(part: types.Part) -> bool:
    return part.text is not None and part.function_call is None


def _usage_of(response: types.GenerateContentResponse) -> Usage:
    metadata = response.usage_metadata
    # O raciocínio do modelo é cobrado como saída, mas vem fora da contagem dos candidatos.
    output = (getattr(metadata, "candidates_token_count", 0) or 0) + (
        getattr(metadata, "thoughts_token_count", 0) or 0
    )
    return Usage(getattr(metadata, "prompt_token_count", 0) or 0, output)


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
