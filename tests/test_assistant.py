from datetime import datetime

from cubo.assistant import Assistant
from cubo.config import Device
from cubo.llm.base import ChatProvider, Exchange, ProviderError, Reply, Usage
from cubo.llm.memory import ConversationMemory
from cubo.llm.prompts import NO_DEVICES, build_system_prompt
from cubo.tools.registry import ToolRegistry
from cubo.usage import UsageTracker


class FakeProvider(ChatProvider):
    name = "falso"
    display_name = "Falso"

    def __init__(self, *, text="", error=None):
        self._text = text
        self._error = error
        self.histories = []

    def reply(self, *, system, history, user_text, tools):
        self.histories.append(history)
        if self._error:
            raise self._error
        return Reply(self._text, Exchange(self.name, (user_text,)))

    def list_models(self):
        return []


def make_assistant(provider, usage=None):
    memory = ConversationMemory(max_exchanges=5, idle_timeout_seconds=600)
    return Assistant(
        provider=provider, tools=ToolRegistry(), memory=memory, system_prompt="", usage=usage
    )


def test_reply_is_cleaned_for_speech_and_remembered():
    provider = FakeProvider(text="**Pronto!** Liguei a luz 💡")
    assistant = make_assistant(provider)

    assert assistant.reply("liga a luz") == "Pronto! Liguei a luz."
    assistant.reply("obrigado")

    assert provider.histories[1] == (Exchange("falso", ("liga a luz",)),)


def test_provider_error_is_spoken_and_not_remembered():
    provider = FakeProvider(error=ProviderError("Sem internet."))
    assistant = make_assistant(provider)

    assert assistant.reply("oi") == "Sem internet."
    assistant.reply("oi de novo")

    assert provider.histories[1] == ()


def test_system_prompt_lists_devices():
    prompt = build_system_prompt(
        "Você é o Cubô.", [Device(entity_id="light.sala", alias="luz da sala")]
    )

    assert prompt.startswith("Você é o Cubô.")
    assert "- luz da sala (light.sala)" in prompt
    assert "Nunca diga que uma ação foi feita" in prompt


def test_system_prompt_without_devices_explains_the_setup():
    assert NO_DEVICES in build_system_prompt("Você é o Cubô.", [])


def test_limit_reached_is_spoken_and_the_provider_is_not_called():
    provider = FakeProvider(text="oi")
    usage = UsageTracker(max_calls_per_minute=1, clock=lambda: datetime(2026, 1, 1))
    assistant = make_assistant(provider, usage)

    assistant.reply("primeiro")
    answer = assistant.reply("segundo")

    assert "limite de chamadas" in answer
    assert len(provider.histories) == 1


def test_tokens_of_each_reply_are_counted():
    class CountingProvider(FakeProvider):
        def reply(self, **kwargs):
            reply = super().reply(**kwargs)
            return Reply(reply.text, reply.exchange, Usage(120, 8))

    usage = UsageTracker()
    assistant = make_assistant(CountingProvider(text="oi"), usage)

    assistant.reply("olá")

    snapshot = usage.snapshot()
    assert (snapshot.calls_today, snapshot.input_tokens_today, snapshot.output_tokens_today) == (
        1,
        120,
        8,
    )
