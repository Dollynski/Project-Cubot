from types import SimpleNamespace

import httpx2
import pytest
from google.genai import errors, types

from cubo.llm.base import ProviderError, Usage
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
        self.models = SimpleNamespace(
            generate_content=self._generate,
            generate_content_stream=self._stream,
            list=self._list,
        )

    def _generate(self, **request):
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
        return self._chunks(step)

    @staticmethod
    def _chunks(step):
        # Um erro no meio da lista acontece durante o streaming, não ao abri-lo.
        for item in step:
            if isinstance(item, Exception):
                raise item
            yield item

    def _list(self):
        return [
            types.Model(name="models/gemini-3.5-flash", supported_actions=["generateContent"]),
            types.Model(name="models/text-embedding", supported_actions=["embedContent"]),
        ]


def ask(client, tools=None, on_text=None):
    provider = GeminiProvider(api_key="AIza-teste", model="gemini-3.5-flash", client=client)
    return provider.reply(
        system="Você é o Cubô.",
        history=(),
        user_text="Oi",
        tools=tools or ToolRegistry(),
        on_text=on_text,
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


def with_usage(message, prompt, candidates, thoughts=None):
    message.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
    )
    return message


def test_sums_token_usage_and_charges_thoughts_as_output():
    client = FakeGenai(
        with_usage(
            model_response(call("c1", "ler_estado", {"dispositivo": "sala"})), 100, 10, thoughts=40
        ),
        with_usage(model_response(types.Part(text="Ligada.")), 150, 20),
    )

    assert ask(client, home_tools()).usage == Usage(250, 70)


def test_response_without_usage_counts_zero_tokens():
    assert ask(FakeGenai(model_response(types.Part(text="Oi")))).usage == Usage()


def chunk(*parts, usage=None):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=usage,
    )


def streamed_parts(reply):
    return list(reply.exchange.messages[-1].parts)


def test_streams_the_text_in_pieces_and_merges_it_into_one_part():
    pieces = []
    client = FakeGenai(
        [chunk(types.Part(text="Olá, ")), chunk(types.Part(text="tudo bem?"))],
    )

    reply = ask(client, on_text=pieces.append)

    assert pieces == ["Olá, ", "tudo bem?"]
    assert reply.text == "Olá, tudo bem?"
    assert [part.text for part in streamed_parts(reply)] == ["Olá, tudo bem?"]


def test_the_streamed_reply_matches_the_plain_one():
    plain = ask(FakeGenai(model_response(types.Part(text="Olá, tudo bem?"))))
    streamed = ask(
        FakeGenai([chunk(types.Part(text="Olá, ")), chunk(types.Part(text="tudo bem?"))]),
        on_text=lambda _piece: None,
    )

    assert streamed.text == plain.text
    assert streamed.exchange.messages[-1] == plain.exchange.messages[-1]


def test_the_thought_signature_survives_the_merge():
    client = FakeGenai(
        [
            chunk(types.Part(text="Oi.")),
            chunk(types.Part(text="", thought_signature=b"assinatura")),
        ]
    )

    reply = ask(client, on_text=lambda _piece: None)

    (part,) = streamed_parts(reply)
    assert part.text == "Oi."
    assert part.thought_signature == b"assinatura"


def test_thought_parts_are_kept_but_never_spoken():
    pieces = []
    client = FakeGenai(
        [
            chunk(types.Part(text="Deixa eu pensar", thought=True)),
            chunk(types.Part(text=" um pouco", thought=True)),
            chunk(types.Part(text="Resposta.")),
        ]
    )

    reply = ask(client, on_text=pieces.append)

    assert pieces == ["Resposta."]
    thought, answer = streamed_parts(reply)
    assert (thought.text, thought.thought) == ("Deixa eu pensar um pouco", True)
    assert answer.text == "Resposta."


def test_streaming_runs_the_function_calls_and_answers_each_one():
    client = FakeGenai(
        [
            chunk(types.Part(text="Vou ver. ")),
            chunk(call("c1", "ler_estado", {"dispositivo": "sala"})),
        ],
        [chunk(types.Part(text="A sala ")), chunk(types.Part(text="está ligada."))],
    )
    pieces = []

    reply = ask(client, home_tools(), on_text=pieces.append)

    assert "".join(pieces) == "Vou ver. A sala está ligada."
    sent = client.requests[1]["contents"]
    response = sent[-1].parts[0].function_response
    assert (response.id, response.name) == ("c1", "ler_estado")
    assert reply.text == "A sala está ligada."


def test_a_blocked_stream_raises_provider_error():
    client = FakeGenai([types.GenerateContentResponse(candidates=[])])

    with pytest.raises(ProviderError, match="não posso ajudar"):
        ask(client, on_text=lambda _piece: None)


def test_streaming_takes_the_usage_from_the_last_chunk_that_has_it():
    usage = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5
    )
    client = FakeGenai(
        [chunk(types.Part(text="Oi ")), chunk(types.Part(text="de novo"), usage=usage)]
    )

    assert ask(client, on_text=lambda _piece: None).usage == Usage(100, 25)


def test_an_error_in_the_middle_of_the_stream_is_translated():
    error = errors.APIError(429, {"error": {"message": "limite"}})
    client = FakeGenai([chunk(types.Part(text="Olá")), error])

    with pytest.raises(ProviderError, match="limitando"):
        ask(client, on_text=lambda _piece: None)


def test_a_connection_error_while_streaming_is_translated():
    client = FakeGenai([httpx2.ConnectError("sem rede", request=REQUEST)])

    with pytest.raises(ProviderError, match="Não consegui me conectar"):
        ask(client, on_text=lambda _piece: None)
