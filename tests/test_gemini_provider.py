from types import SimpleNamespace

import httpx2
import pytest
from google.genai import errors, types

from cubo.llm.base import ProviderError
from cubo.llm.gemini import GeminiProvider
from cubo.tools.registry import ToolRegistry
from tests.fakes import REQUEST, home_tools


def model_response(*parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def call(call_id, name, args):
    return types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args))


class FakeGenai:
    def __init__(self, *responses_or_errors):
        self.requests = []
        self._script = list(responses_or_errors)
        self.models = SimpleNamespace(generate_content=self._generate, list=self._list)

    def _generate(self, **request):
        self.requests.append(request)
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def _list(self):
        return [
            types.Model(name="models/gemini-3.5-flash", supported_actions=["generateContent"]),
            types.Model(name="models/text-embedding", supported_actions=["embedContent"]),
        ]


def ask(client, tools=None):
    provider = GeminiProvider(api_key="AIza-teste", model="gemini-3.5-flash", client=client)
    return provider.reply(
        system="Você é o Cubô.", history=(), user_text="Oi", tools=tools or ToolRegistry()
    )


def test_plain_reply_ignores_thought_parts():
    client = FakeGenai(
        model_response(types.Part(text="pensando...", thought=True), types.Part(text="Olá!"))
    )

    reply = ask(client)

    assert reply.text == "Olá!"
    config = client.requests[0]["config"]
    assert config.system_instruction == "Você é o Cubô."
    assert config.tools is None
    assert config.automatic_function_calling.disable is True


def test_answers_each_function_call_with_matching_id_and_name():
    client = FakeGenai(
        model_response(
            call("c1", "ler_estado", {"dispositivo": "sala"}),
            call("c2", "quebrada", {}),
        ),
        model_response(types.Part(text="A sala está ligada.")),
    )

    reply = ask(client, tools=home_tools())

    assert reply.text == "A sala está ligada."
    declarations = client.requests[0]["config"].tools[0].function_declarations
    assert [d.name for d in declarations] == ["ler_estado", "quebrada"]
    answers = client.requests[1]["contents"][-1]
    assert answers.role == "user"
    assert [
        (p.function_response.id, p.function_response.name, p.function_response.response)
        for p in answers.parts
    ] == [
        ("c1", "ler_estado", {"output": "sala: ligado"}),
        ("c2", "quebrada", {"error": "dispositivo indisponível"}),
    ]


def test_blocked_response_raises_refusal():
    with pytest.raises(ProviderError, match="não posso ajudar"):
        ask(FakeGenai(types.GenerateContentResponse(candidates=[])))


def test_lists_only_chat_models_without_prefix():
    provider = GeminiProvider(api_key="AIza-teste", model="gemini-3.5-flash", client=FakeGenai())

    assert provider.list_models() == ["gemini-3.5-flash"]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid."}}),
            "recusou a chave",
        ),
        (errors.ClientError(429, {"error": {"code": 429, "message": "quota"}}), "limitando"),
        (errors.ServerError(503, {"error": {"code": 503, "message": "busy"}}), "HTTP 503"),
        (httpx2.ConnectError("offline", request=REQUEST), "conectar ao serviço Gemini"),
    ],
)
def test_translates_sdk_errors(error, message):
    with pytest.raises(ProviderError, match=message):
        ask(FakeGenai(error))
