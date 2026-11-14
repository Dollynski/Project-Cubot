from types import SimpleNamespace

import anthropic
import pytest

from cubo.llm.base import Exchange, ProviderError, Usage
from cubo.llm.claude import FALLBACK_BETA, THINKING_BINDING_BETA, ClaudeProvider
from cubo.tools.registry import ToolRegistry
from tests.fakes import REQUEST, home_tools, http_response


def text(value):
    return SimpleNamespace(type="text", text=value)


def tool_use(call_id, name, arguments):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=arguments)


def response(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


class FakeAnthropic:
    def __init__(self, *responses_or_errors):
        self.requests = []
        self._script = list(responses_or_errors)
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(create=self._create, stream=self._stream)
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
    """Parecido com o fluxo do SDK: entrega o texto em pedaços e a mensagem final montada."""

    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    @property
    def text_stream(self):
        for block in self._message.content:
            if block.type == "text":
                text = block.text
                yield from (text[start : start + 4] for start in range(0, len(text), 4))

    def get_final_message(self):
        return self._message


def provider(client, model="claude-opus-5-5"):
    return ClaudeProvider(api_key="sk-teste", model=model, client=client)


def ask(claude, history=(), tools=None, on_text=None):
    return claude.reply(
        system="Você é o Cubô.",
        history=history,
        user_text="Oi",
        tools=tools or ToolRegistry(),
        on_text=on_text,
    )


def test_plain_reply_and_request_options():
    client = FakeAnthropic(response("end_turn", text("Olá!")))

    reply = ask(provider(client))

    assert reply.text == "Olá!"
    assert reply.exchange.provider == "claude"
    assert [m["role"] for m in reply.exchange.messages] == ["user", "assistant"]
    request = client.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "low"}
    assert request["thinking"]["block_binding"] == {"prefix_mismatch_behavior": "drop_block"}
    assert request["betas"] == [THINKING_BINDING_BETA, FALLBACK_BETA]
    assert request["fallbacks"] == "default"
    assert "tools" not in request
    assert "temperature" not in request


def test_model_without_server_fallback_does_not_send_it():
    client = FakeAnthropic(response("end_turn", text("Olá!")))

    ask(provider(client, model="claude-haiku-5-5"))

    assert client.requests[0]["betas"] == [THINKING_BINDING_BETA]
    assert "fallbacks" not in client.requests[0]


def test_runs_parallel_tools_and_returns_all_results_in_one_message():
    client = FakeAnthropic(
        response(
            "tool_use",
            text("Vou ver."),
            tool_use("t1", "ler_estado", {"dispositivo": "sala"}),
            tool_use("t2", "quebrada", {}),
        ),
        response("end_turn", text("A sala está ligada.")),
    )

    reply = ask(provider(client), tools=home_tools())

    assert reply.text == "A sala está ligada."
    results_message = client.requests[1]["messages"][-1]
    assert results_message["role"] == "user"
    assert results_message["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "sala: ligado", "is_error": False},
        {
            "type": "tool_result",
            "tool_use_id": "t2",
            "content": "dispositivo indisponível",
            "is_error": True,
        },
    ]
    assert [m["role"] for m in reply.exchange.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_assistant_content_is_kept_unchanged_for_thinking_blocks():
    thinking = SimpleNamespace(type="thinking", thinking="", signature="assinatura")
    original = response("end_turn", thinking, text("Oi!"))
    client = FakeAnthropic(original)

    reply = ask(provider(client))

    assert reply.exchange.messages[1]["content"] is original.content


def test_sends_only_claude_history_before_the_new_message():
    client = FakeAnthropic(response("end_turn", text("De nada.")))
    history = [
        Exchange("gemini", ("mensagem de outro provedor",)),
        Exchange("claude", ({"role": "user", "content": "Obrigado"}, {"role": "assistant"})),
    ]

    ask(provider(client), history=history)

    sent = client.requests[0]["messages"]
    assert sent[:2] == [{"role": "user", "content": "Obrigado"}, {"role": "assistant"}]
    assert sent[2] == {"role": "user", "content": "Oi"}


def test_refusal_raises_provider_error():
    client = FakeAnthropic(response("refusal"))

    with pytest.raises(ProviderError, match="não posso ajudar"):
        ask(provider(client))


def test_stops_after_too_many_tool_rounds():
    loop = response("tool_use", tool_use("t", "ler_estado", {"dispositivo": "sala"}))
    client = FakeAnthropic(*[loop] * 5)

    with pytest.raises(ProviderError, match="não consegui concluir"):
        ask(provider(client), tools=home_tools())


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            anthropic.AuthenticationError("x", response=http_response(401), body=None),
            "recusou a chave",
        ),
        (anthropic.NotFoundError("x", response=http_response(404), body=None), "não encontrou"),
        (anthropic.RateLimitError("x", response=http_response(429), body=None), "limitando"),
        (anthropic.InternalServerError("x", response=http_response(500), body=None), "HTTP 500"),
        (anthropic.APIConnectionError(request=REQUEST), "conectar ao serviço Claude"),
    ],
)
def test_translates_sdk_errors(error, message):
    with pytest.raises(ProviderError, match=message):
        ask(provider(FakeAnthropic(error)))


def with_usage(message, *, input_tokens, output_tokens, cache_read=0, cache_creation=0):
    message.usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )
    return message


def test_sums_token_usage_including_the_prompt_cache():
    client = FakeAnthropic(
        with_usage(
            response("tool_use", tool_use("t1", "ler_estado", {"dispositivo": "sala"})),
            input_tokens=100,
            output_tokens=10,
            cache_creation=500,
        ),
        with_usage(
            response("end_turn", text("Ligada.")),
            input_tokens=20,
            output_tokens=5,
            cache_read=600,
        ),
    )

    assert ask(provider(client), tools=home_tools()).usage == Usage(1220, 15)


def test_response_without_usage_counts_zero_tokens():
    assert ask(provider(FakeAnthropic(response("end_turn", text("Oi"))))).usage == Usage()


def test_streams_the_text_in_pieces_and_returns_the_same_reply():
    streamed = FakeAnthropic(response("end_turn", text("Olá, tudo bem?")))
    plain = FakeAnthropic(response("end_turn", text("Olá, tudo bem?")))
    pieces = []

    reply = ask(provider(streamed), on_text=pieces.append)

    assert "".join(pieces) == "Olá, tudo bem?"
    assert len(pieces) > 1
    assert reply == ask(provider(plain))


def test_streaming_sends_the_same_options_as_the_plain_call():
    streamed = FakeAnthropic(response("end_turn", text("Oi")))
    plain = FakeAnthropic(response("end_turn", text("Oi")))

    ask(provider(streamed), on_text=lambda _piece: None)
    ask(provider(plain))

    request = dict(streamed.requests[0])
    assert request.pop("streamed") is True
    assert request == plain.requests[0]


def test_streaming_runs_the_tools_and_only_the_final_text_is_spoken():
    client = FakeAnthropic(
        response("tool_use", tool_use("t1", "ler_estado", {"dispositivo": "sala"})),
        response("end_turn", text("A sala está ligada.")),
    )
    pieces = []

    reply = ask(provider(client), tools=home_tools(), on_text=pieces.append)

    assert "".join(pieces) == "A sala está ligada."
    assert reply.text == "A sala está ligada."
    assert [request["streamed"] for request in client.requests] == [True, True]


def test_streaming_translates_sdk_errors():
    error = anthropic.APIConnectionError(request=REQUEST)

    with pytest.raises(ProviderError, match="Não consegui me conectar"):
        ask(provider(FakeAnthropic(error)), on_text=lambda _piece: None)


def test_streaming_counts_the_tokens_of_the_final_message():
    message = with_usage(response("end_turn", text("Oi")), input_tokens=10, output_tokens=2)

    reply = ask(provider(FakeAnthropic(message)), on_text=lambda _piece: None)

    assert reply.usage == Usage(10, 2)
