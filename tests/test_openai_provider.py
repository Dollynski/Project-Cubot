from types import SimpleNamespace

import openai
import pytest
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion

from cubo.llm.base import ProviderError, Usage
from cubo.llm.openai_compatible import OpenAICompatibleProvider
from cubo.tools.registry import ToolRegistry
from tests.fakes import REQUEST, home_tools, http_response


def completion(content=None, tool_calls=None, refusal=None):
    message = {"role": "assistant", "content": content, "refusal": refusal}
    if tool_calls:
        message["tool_calls"] = [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}
            for call_id, name, args in tool_calls
        ]
    return ChatCompletion.model_validate(
        {
            "id": "resposta",
            "object": "chat.completion",
            "created": 0,
            "model": "modelo",
            "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        }
    )


class FakeOpenAI:
    def __init__(self, *responses_or_errors):
        self.requests = []
        self._script = list(responses_or_errors)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create, stream=self._stream)
        )

    def _create(self, **request):
        self.requests.append(request)
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def _stream(self, **request):
        self.requests.append({**request, "streamed": True})
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return FakeStream(step)


class FakeStream:
    """Parecido com o fluxo do SDK: eventos de texto e a resposta final montada."""

    def __init__(self, completion):
        self._completion = completion

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def __iter__(self):
        yield SimpleNamespace(type="chunk")
        text = self._completion.choices[0].message.content or ""
        for start in range(0, len(text), 4):
            yield SimpleNamespace(type="content.delta", delta=text[start : start + 4])
        yield SimpleNamespace(type="content.done")

    def get_final_completion(self):
        return self._completion


def ask(client, tools=None, name="openai", on_text=None):
    provider = OpenAICompatibleProvider(
        name=name, display_name=name.capitalize(), api_key="sk-teste", model="m", client=client
    )
    return provider.reply(
        system="Você é o Cubô.",
        history=(),
        user_text="Oi",
        tools=tools or ToolRegistry(),
        on_text=on_text,
    )


def test_plain_reply_sends_system_message_first():
    client = FakeOpenAI(completion("Olá!"))

    reply = ask(client)

    assert reply.text == "Olá!"
    assert client.requests[0]["messages"][0] == {"role": "system", "content": "Você é o Cubô."}
    assert "tools" not in client.requests[0]
    # O prompt de sistema é refeito a cada pedido; não entra no histórico.
    assert [m["role"] for m in reply.exchange.messages] == ["user", "assistant"]


def test_runs_tools_and_answers_each_call():
    client = FakeOpenAI(
        completion(
            tool_calls=[
                ("call_1", "ler_estado", '{"dispositivo": "sala"}'),
                ("call_2", "quebrada", "{}"),
                ("call_3", "ler_estado", "não é json"),
            ]
        ),
        completion("A sala está ligada."),
    )

    reply = ask(client, tools=home_tools())

    assert reply.text == "A sala está ligada."
    sent = client.requests[1]["messages"]
    assert sent[2]["tool_calls"][0]["function"]["name"] == "ler_estado"
    assert sent[3:] == [
        {"role": "tool", "tool_call_id": "call_1", "content": "sala: ligado"},
        {"role": "tool", "tool_call_id": "call_2", "content": "Erro: dispositivo indisponível"},
        {
            "role": "tool",
            "tool_call_id": "call_3",
            "content": "Erro: os argumentos da ferramenta não são um objeto JSON válido.",
        },
    ]


def test_refusal_raises_provider_error():
    with pytest.raises(ProviderError, match="não posso ajudar"):
        ask(FakeOpenAI(completion(refusal="Não posso.")))


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            openai.AuthenticationError("x", response=http_response(401), body=None),
            "recusou a chave",
        ),
        (openai.NotFoundError("x", response=http_response(404), body=None), "não encontrou"),
        (openai.APIConnectionError(request=REQUEST), "conectar ao serviço Ollama"),
    ],
)
def test_translates_sdk_errors_with_the_provider_name(error, message):
    with pytest.raises(ProviderError, match=message):
        ask(FakeOpenAI(error), name="ollama")


def with_usage(response, prompt_tokens, completion_tokens):
    usage = CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return response.model_copy(update={"usage": usage})


def test_sums_token_usage_across_tool_rounds():
    client = FakeOpenAI(
        with_usage(
            completion(tool_calls=[("c1", "ler_estado", '{"dispositivo": "sala"}')]), 100, 10
        ),
        with_usage(completion("Ligada."), 150, 20),
    )

    assert ask(client, home_tools()).usage == Usage(250, 30)


def test_server_without_usage_counts_zero_tokens():
    # O Ollama e outros servidores compatíveis podem não informar o uso.
    assert ask(FakeOpenAI(completion("Oi"))).usage == Usage()


def test_streams_the_text_in_pieces_and_returns_the_same_reply():
    pieces = []

    streamed = ask(FakeOpenAI(completion("Olá, tudo bem?")), on_text=pieces.append)

    assert "".join(pieces) == "Olá, tudo bem?"
    assert len(pieces) > 1
    assert streamed == ask(FakeOpenAI(completion("Olá, tudo bem?")))


def test_streaming_asks_the_server_to_report_the_usage():
    client = FakeOpenAI(completion("Oi"))

    ask(client, on_text=lambda _piece: None)

    assert client.requests[0]["stream_options"] == {"include_usage": True}
    assert client.requests[0]["streamed"] is True


def test_streaming_runs_the_tools_and_only_the_final_text_is_spoken():
    client = FakeOpenAI(
        completion(tool_calls=[("c1", "ler_estado", '{"dispositivo": "sala"}')]),
        completion("A sala está ligada."),
    )
    pieces = []

    reply = ask(client, home_tools(), on_text=pieces.append)

    assert "".join(pieces) == "A sala está ligada."
    assert reply.text == "A sala está ligada."


def test_streaming_translates_sdk_errors():
    error = openai.APIConnectionError(request=REQUEST)

    with pytest.raises(ProviderError, match="Não consegui me conectar"):
        ask(FakeOpenAI(error), on_text=lambda _piece: None)


def test_streaming_refusal_raises_provider_error():
    with pytest.raises(ProviderError, match="não posso ajudar"):
        ask(FakeOpenAI(completion(refusal="Não posso.")), on_text=lambda _piece: None)
