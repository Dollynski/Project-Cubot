from datetime import datetime, timedelta

import pytest

from cubo.llm.base import ProviderError, Usage
from cubo.usage import UsageTracker


class Clock:
    def __init__(self, start=datetime(2026, 11, 13, 10, 0, 0)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


def test_blocks_calls_over_the_per_minute_limit_and_frees_them_later():
    clock = Clock()
    tracker = UsageTracker(max_calls_per_minute=2, clock=clock)
    tracker.acquire()
    tracker.acquire()

    with pytest.raises(ProviderError, match="por minuto"):
        tracker.acquire()

    clock.advance(seconds=61)
    tracker.acquire()


def test_blocks_calls_over_the_per_day_limit_until_tomorrow():
    clock = Clock()
    tracker = UsageTracker(max_calls_per_day=2, clock=clock)
    tracker.acquire()
    clock.advance(hours=2)
    tracker.acquire()
    clock.advance(hours=2)

    with pytest.raises(ProviderError, match="por dia"):
        tracker.acquire()

    clock.advance(days=1)
    tracker.acquire()
    assert tracker.snapshot().calls_today == 1


def test_a_blocked_call_is_not_counted():
    tracker = UsageTracker(max_calls_per_minute=1, clock=Clock())
    tracker.acquire()
    with pytest.raises(ProviderError):
        tracker.acquire()

    assert tracker.snapshot().calls_today == 1


def test_zero_means_no_limit():
    tracker = UsageTracker(max_calls_per_minute=0, max_calls_per_day=0, clock=Clock())

    for _ in range(100):
        tracker.acquire()

    assert tracker.snapshot().calls_today == 100


def test_limits_can_change_while_running():
    tracker = UsageTracker(max_calls_per_minute=1, clock=Clock())
    tracker.acquire()

    tracker.set_limits(max_calls_per_minute=5, max_calls_per_day=0)
    tracker.acquire()

    assert tracker.snapshot().max_calls_per_minute == 5


def test_counts_tokens():
    tracker = UsageTracker(clock=Clock())

    tracker.add_tokens(Usage(100, 10))
    tracker.add_tokens(Usage(50, 5))

    snapshot = tracker.snapshot()
    assert (snapshot.input_tokens_today, snapshot.output_tokens_today) == (150, 15)


def test_the_day_total_survives_a_restart(tmp_path):
    path = tmp_path / "usage.toml"
    clock = Clock()
    first = UsageTracker(path, max_calls_per_day=2, clock=clock)
    first.acquire()
    first.add_tokens(Usage(100, 10))

    second = UsageTracker(path, max_calls_per_day=2, clock=clock)

    snapshot = second.snapshot()
    assert (snapshot.calls_today, snapshot.input_tokens_today) == (1, 100)
    second.acquire()
    with pytest.raises(ProviderError):
        second.acquire()


def test_a_new_day_starts_from_zero_after_a_restart(tmp_path):
    path = tmp_path / "usage.toml"
    clock = Clock()
    UsageTracker(path, clock=clock).acquire()

    clock.advance(days=1)

    assert UsageTracker(path, clock=clock).snapshot().calls_today == 0
