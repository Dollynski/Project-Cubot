from cubo.llm.base import Exchange
from cubo.llm.memory import ConversationMemory


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def exchange(number):
    return Exchange(provider="gemini", messages=(f"mensagem {number}",))


def test_keeps_only_the_latest_exchanges():
    memory = ConversationMemory(max_exchanges=2, idle_timeout_seconds=60)
    for number in range(3):
        memory.add(exchange(number))

    assert memory.history() == (exchange(1), exchange(2))


def test_forgets_everything_after_idle_timeout():
    clock = FakeClock()
    memory = ConversationMemory(max_exchanges=5, idle_timeout_seconds=60, clock=clock)
    memory.add(exchange(1))

    clock.now = 59
    assert memory.history() == (exchange(1),)
    clock.now = 61
    assert memory.history() == ()
