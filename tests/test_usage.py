import subprocess
import sys
import threading
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


# ---- vários processos do Cubô no mesmo dia: o total é um só


def test_two_trackers_on_the_same_file_share_the_daily_total(tmp_path):
    path = tmp_path / "usage.toml"
    service = UsageTracker(path, max_calls_per_day=3, clock=Clock())
    text_mode = UsageTracker(path, max_calls_per_day=3, clock=Clock())
    service.acquire()
    service.acquire()

    text_mode.acquire()

    assert text_mode.snapshot().calls_today == 3
    with pytest.raises(ProviderError, match="por dia"):
        service.acquire()


def test_tokens_from_every_tracker_add_up(tmp_path):
    path = tmp_path / "usage.toml"
    first, second = UsageTracker(path, clock=Clock()), UsageTracker(path, clock=Clock())

    first.add_tokens(Usage(100, 10))
    second.add_tokens(Usage(50, 5))
    first.add_tokens(Usage(1, 1))

    for tracker in (first, second):
        snapshot = tracker.snapshot()
        assert (snapshot.input_tokens_today, snapshot.output_tokens_today) == (151, 16)


def test_the_snapshot_shows_what_another_process_did(tmp_path):
    path = tmp_path / "usage.toml"
    panel = UsageTracker(path, clock=Clock())
    UsageTracker(path, clock=Clock()).acquire()

    assert panel.snapshot().calls_today == 1


def test_a_tracker_that_woke_up_late_does_not_erase_the_other_processes_day(tmp_path):
    path = tmp_path / "usage.toml"
    yesterday = Clock()
    sleeping = UsageTracker(path, clock=yesterday)
    sleeping.acquire()
    today = Clock(yesterday.now + timedelta(days=1))
    UsageTracker(path, clock=today).acquire()

    yesterday.advance(days=1)  # o primeiro só acorda hoje
    sleeping.acquire()

    assert sleeping.snapshot().calls_today == 2


def test_the_per_minute_limit_belongs_to_each_process(tmp_path):
    path = tmp_path / "usage.toml"
    first = UsageTracker(path, max_calls_per_minute=1, clock=Clock())
    second = UsageTracker(path, max_calls_per_minute=1, clock=Clock())

    first.acquire()
    second.acquire()  # outro processo: a janela de um minuto é só da memória de cada um

    assert second.snapshot().calls_today == 2


def test_concurrent_threads_never_lose_a_call(tmp_path):
    path = tmp_path / "usage.toml"
    trackers = [UsageTracker(path, clock=Clock()) for _ in range(4)]

    def spend(tracker):
        for _ in range(25):
            tracker.acquire()
            tracker.add_tokens(Usage(10, 1))

    threads = [threading.Thread(target=spend, args=(tracker,)) for tracker in trackers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = UsageTracker(path, clock=Clock()).snapshot()
    assert (snapshot.calls_today, snapshot.input_tokens_today) == (100, 1000)


def test_concurrent_processes_never_lose_a_call(tmp_path):
    path = tmp_path / "usage.toml"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from cubo.llm.base import Usage\n"
        "from cubo.usage import UsageTracker\n"
        "tracker = UsageTracker(Path(sys.argv[1]))\n"
        "for _ in range(30):\n"
        "    tracker.acquire()\n"
        "    tracker.add_tokens(Usage(5, 1))\n"
    )
    processes = [subprocess.Popen([sys.executable, "-c", script, str(path)]) for _ in range(3)]
    for process in processes:
        assert process.wait(timeout=60) == 0

    snapshot = UsageTracker(path).snapshot()
    assert (snapshot.calls_today, snapshot.input_tokens_today) == (90, 450)
