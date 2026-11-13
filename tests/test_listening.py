import numpy as np

from cubo.voice.audio import FRAME_SAMPLES
from cubo.voice.listening import ListeningLimits, SpeechDetector, UtteranceRecorder

FRAME_SECONDS = 0.08


def frame(value: float = 0.0) -> np.ndarray:
    return np.full(FRAME_SAMPLES, value, np.float32)


def loudness_model(audio: np.ndarray) -> np.ndarray:
    """Falso Silero: a "probabilidade" de cada janela de 512 amostras é o seu pico."""
    return np.abs(audio).reshape(-1, 512).max(axis=1)


def test_detector_hears_loud_audio_and_not_silence():
    detector = SpeechDetector(model=loudness_model)

    assert detector.is_speech(frame(0.9)) is True
    detector.reset()
    assert detector.is_speech(frame(0.0)) is False


def test_detector_respects_the_threshold():
    assert SpeechDetector(threshold=0.5, model=loudness_model).is_speech(frame(0.4)) is False
    assert SpeechDetector(threshold=0.3, model=loudness_model).is_speech(frame(0.4)) is True


def test_detector_forgets_past_audio_on_reset():
    detector = SpeechDetector(model=loudness_model)
    detector.is_speech(frame(0.9))

    detector.reset()

    assert detector.is_speech(frame(0.0)) is False


class ScriptedDetector:
    """Responde, quadro a quadro, o que o roteiro mandar."""

    def __init__(self, speech: list[bool]) -> None:
        self._speech = iter(speech)
        self.resets = 0

    def is_speech(self, _frame: np.ndarray) -> bool:
        return next(self._speech)

    def reset(self) -> None:
        self.resets += 1


def record(speech: list[bool], limits: ListeningLimits):
    detector = ScriptedDetector(speech)
    frames = iter(frame(index) for index in range(len(speech)))
    audio = UtteranceRecorder(detector, limits).record(frames)
    return audio, frames, detector


def test_recording_stops_after_the_silence_that_follows_speech():
    limits = ListeningLimits(silence_seconds=0.2)

    audio, remaining, detector = record(
        [False, True, True, False, False, False, True, True], limits
    )

    # Quadros 0 a 5: o silêncio de 3 quadros (0,24 s) encerra, e o resto não é consumido.
    assert len(audio) == 6 * FRAME_SAMPLES
    assert [chunk[0] for chunk in remaining] == [6.0, 7.0]
    assert detector.resets == 1


def test_returns_none_when_nobody_speaks_in_time():
    limits = ListeningLimits(wait_seconds=0.2)

    audio, remaining, _ = record([False] * 6, limits)

    assert audio is None
    assert len(list(remaining)) == 3


def test_returns_none_when_the_audio_ends_without_speech():
    audio, _, _ = record([False, False], ListeningLimits(wait_seconds=5.0))

    assert audio is None


def test_long_speech_is_cut_at_the_maximum_duration():
    limits = ListeningLimits(silence_seconds=0.2, max_seconds=0.2)

    audio, _, _ = record([True] * 6, limits)

    assert len(audio) == 3 * FRAME_SAMPLES


def test_short_pauses_do_not_end_the_request():
    limits = ListeningLimits(silence_seconds=0.2)

    audio, _, _ = record([True, False, True, False, True, False, False, False], limits)

    assert len(audio) == 8 * FRAME_SAMPLES
