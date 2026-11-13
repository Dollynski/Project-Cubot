from types import SimpleNamespace

import numpy as np

from cubo.voice.stt import Transcriber


def segment(text: str, no_speech_prob: float = 0.0):
    return SimpleNamespace(text=text, no_speech_prob=no_speech_prob)


class FakeWhisper:
    def __init__(self, segments):
        self._segments = segments
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append(options)
        # Como no faster-whisper: um gerador, que só trabalha quando é percorrido.
        return (item for item in self._segments), SimpleNamespace(language="pt")


def transcriber(segments, tmp_path):
    return Transcriber("base", "int8", tmp_path, model=FakeWhisper(segments))


AUDIO = np.zeros(16_000, np.float32)


def test_joins_every_segment(tmp_path):
    result = transcriber([segment(" Acende "), segment("a luz. ")], tmp_path).transcribe(AUDIO)

    assert result == "Acende a luz."


def test_drops_segments_the_model_thinks_are_not_speech(tmp_path):
    segments = [segment("Obrigado por assistir", no_speech_prob=0.9), segment("Que horas são?")]

    assert transcriber(segments, tmp_path).transcribe(AUDIO) == "Que horas são?"


def test_silence_gives_empty_text(tmp_path):
    assert transcriber([], tmp_path).transcribe(AUDIO) == ""
    assert transcriber([segment("   ")], tmp_path).transcribe(AUDIO) == ""


def test_transcribes_in_portuguese_without_a_second_vad_pass(tmp_path):
    model = FakeWhisper([segment("oi")])

    Transcriber("base", "int8", tmp_path, model=model).transcribe(AUDIO)

    assert model.calls[0]["language"] == "pt"
    assert model.calls[0]["vad_filter"] is False


def test_warm_up_runs_a_silent_transcription_without_failing(tmp_path):
    model = FakeWhisper([])

    Transcriber("base", "int8", tmp_path, model=model).warm_up()

    assert len(model.calls) == 1
