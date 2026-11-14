import pytest

from cubo.voice.timing import Stopwatch, Timing


class Clock:
    def __init__(self):
        self.now = 50.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_measures_each_stage_from_the_start():
    clock = Clock()
    stopwatch = Stopwatch(clock)
    clock.advance(0.6)
    stopwatch.mark("transcribed")
    clock.advance(0.8)
    stopwatch.mark("first_text")
    clock.advance(0.4)
    stopwatch.mark("first_sound")
    clock.advance(0.7)
    stopwatch.mark("replied")
    clock.advance(2.0)
    stopwatch.mark("done")

    timing = stopwatch.timing()

    assert timing.transcription == pytest.approx(0.6)
    assert timing.first_text == pytest.approx(0.8)  # depois da transcrição
    assert timing.first_sound == pytest.approx(1.8)  # desde o fim da gravação
    assert timing.reply == pytest.approx(1.9)
    assert timing.total == pytest.approx(4.5)


def test_only_the_first_mark_of_a_stage_counts():
    clock = Clock()
    stopwatch = Stopwatch(clock)
    clock.advance(1.0)
    stopwatch.mark("first_sound")
    clock.advance(5.0)
    stopwatch.mark("first_sound")

    assert stopwatch.at("first_sound") == pytest.approx(1.0)


def test_stages_that_did_not_happen_are_absent():
    clock = Clock()
    stopwatch = Stopwatch(clock)
    clock.advance(0.5)
    stopwatch.mark("transcribed")
    clock.advance(1.0)
    stopwatch.mark("replied")
    stopwatch.mark("done")

    timing = stopwatch.timing()

    assert timing.first_text is None
    assert timing.first_sound is None
    assert timing.reply == pytest.approx(1.0)


def test_timing_is_a_plain_value():
    assert Timing(0.5, 1.0, 2.0, 1.5, 3.0) == Timing(0.5, 1.0, 2.0, 1.5, 3.0)
