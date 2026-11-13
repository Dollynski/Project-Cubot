from types import SimpleNamespace

import openai
import pytest
from openai.types.chat import ChatCompletion

from cubo.llm.base import ProviderError
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
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append(request)
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def ask(client, tools=None, name="openai"):
    provider = OpenAICompatibleProvider(
        name=name, display_name=name.capitalize(), api_key="sk-teste", model="m", client=client
    )
    return provider.reply(
        system="Você é o Cubô.", history=(), user_text="Oi", tools=tools or ToolRegistry()
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
