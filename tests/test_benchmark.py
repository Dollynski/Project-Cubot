import numpy as np
import pytest

from cubo.voice.audio import SAMPLE_RATE, AudioClip
from cubo.voice.benchmark import (
    ModelResult,
    Synthesis,
    Transcription,
    benchmark_models,
    format_report,
    synthesize_phrases,
    word_error_rate,
)


@pytest.mark.parametrize(
    "reference, heard, expected",
    [
        ("acende a luz", "acende a luz", 0.0),
        ("Acende a luz!", "acende a luz", 0.0),  # maiúsculas e pontuação não contam
        ("acende a luz", "assende a luz", 1 / 3),  # uma palavra trocada
        ("acende a luz da sala", "acende a luz", 2 / 5),  # duas faltando
        ("acende a luz", "acende a luz da sala", 2 / 3),  # duas sobrando
        ("acende a luz", "", 1.0),
        ("", "", 0.0),
        ("", "qualquer coisa", 1.0),
    ],
)
def test_word_error_rate(reference, heard, expected):
    assert word_error_rate(reference, heard) == pytest.approx(expected)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeTranscriber:
    """Cada modelo "leva" um tempo fixo e erra o que o roteiro mandar."""

    def __init__(self, clock, seconds, mistakes=()):
        self._clock = clock
        self._seconds = seconds
        self._mistakes = dict(mistakes)
        self.warm_ups = 0
        self.transcriptions = 0

    def warm_up(self):
        self.warm_ups += 1
        self._clock.now += 100  # o aquecimento não pode entrar na conta

    def transcribe(self, audio):
        self.transcriptions += 1
        self._clock.now += self._seconds
        return self._mistakes.get(len(audio), "frase certa")


def clip(seconds, phrase="frase certa"):
    return phrase, np.zeros(int(SAMPLE_RATE * seconds), np.float32)


def test_measures_each_model_after_warming_it_up():
    clock = FakeClock()
    made = {}

    def make(model):
        clock.now += {"base": 1.0, "small": 3.0}[model]
        made[model] = FakeTranscriber(clock, {"base": 0.5, "small": 1.5}[model])
        return made[model]

    results = benchmark_models(
        ["base", "small"], make, [clip(2.0), clip(4.0)], repetitions=1, clock=clock
    )

    base, small = results
    assert (base.model, base.load_seconds, base.mean_seconds) == ("base", 1.0, 0.5)
    assert (small.model, small.load_seconds, small.mean_seconds) == ("small", 3.0, 1.5)
    assert base.real_time_factor == pytest.approx(1.0 / 6.0)
    assert made["base"].warm_ups == 1


def test_repeats_each_phrase_the_requested_number_of_times():
    clock = FakeClock()
    transcriber = FakeTranscriber(clock, 0.5)

    (result,) = benchmark_models(
        ["base"], lambda _model: transcriber, [clip(1.0), clip(2.0)], repetitions=3, clock=clock
    )

    assert transcriber.transcriptions == 6
    assert len(result.transcriptions) == 6


def test_reports_how_much_each_model_gets_wrong():
    clock = FakeClock()
    transcriber = FakeTranscriber(clock, 0.1, mistakes={SAMPLE_RATE * 2: "frase errada"})

    (result,) = benchmark_models(
        ["base"], lambda _model: transcriber, [clip(1.0), clip(2.0)], clock=clock
    )

    assert result.mean_error == pytest.approx((0 + 0.5) / 2)


def test_synthesizes_every_phrase_and_measures_it():
    clock = FakeClock()

    class FakeSynthesizer:
        def synthesize(self, text):
            clock.now += 0.25
            return AudioClip(np.zeros(SAMPLE_RATE * 2, np.float32), SAMPLE_RATE)

    clips, timings = synthesize_phrases(FakeSynthesizer(), ["Oi.", "Tchau."], clock=clock)

    assert [phrase for phrase, _ in clips] == ["Oi.", "Tchau."]
    assert all(len(audio) == SAMPLE_RATE * 2 for _, audio in clips)
    assert timings == [Synthesis("Oi.", 2.0, 0.25), Synthesis("Tchau.", 2.0, 0.25)]


def test_the_report_lists_every_model_and_the_synthesis():
    results = [
        ModelResult("base", 1.2, [Transcription("acende a luz", "acende a luz", 2.0, 0.6)]),
        ModelResult("small", 3.4, [Transcription("acende a luz", "assende a luz", 2.0, 1.8)]),
    ]

    report = format_report(results, [Synthesis("Oi.", 1.0, 0.2)])

    assert "base" in report and "small" in report
    assert "1.2s" in report and "3.4s" in report
    assert "0%" in report and "33%" in report
    assert "1 frases" in report
