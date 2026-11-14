import numpy as np
import pytest

from cubo.voice.audio import AudioClip
from cubo.voice.events import Heard, Replied, State, StateChanged, Timed
from cubo.voice.loop import VoiceLoop
from cubo.voice.tts import SynthesisError

SILENCE = np.array([0.0], np.float32)
WAKE = np.array([1.0], np.float32)
SPEECH = np.array([0.5], np.float32)


class ScriptedMicrophone:
    def __init__(self, frames):
        self._frames = frames
        self.flushes = 0

    def frames(self, _stop):
        yield from self._frames

    def flush(self):
        self.flushes += 1


class FakeWakeWord:
    def __init__(self):
        self.resets = 0

    def detected(self, frame):
        return bool(frame[0] == 1.0)

    def reset(self):
        self.resets += 1


class TwoFrameRecorder:
    """Grava os dois quadros seguintes à wake word, ou nada, se configurado."""

    def __init__(self, hears_speech=True):
        self._hears_speech = hears_speech

    def record(self, frames):
        if not self._hears_speech:
            return None
        return np.concatenate([next(frames), next(frames)])


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeTranscriber:
    def __init__(self, text="acende a luz", clock=None, seconds=0.0):
        self._text = text
        self._clock = clock
        self._seconds = seconds

    def transcribe(self, _audio):
        if self._clock:
            self._clock.now += self._seconds
        return self._text


class FakeAssistant:
    def __init__(self, pieces=(), clock=None):
        self.heard = []
        self.received_callback = []
        self._pieces = pieces
        self._clock = clock

    def reply(self, text, on_text=None):
        self.heard.append(text)
        self.received_callback.append(on_text is not None)
        if self._clock:
            self._clock.now += 1.0
        for piece in self._pieces if on_text else ():
            on_text(piece)
        if self._clock:
            self._clock.now += 1.0
        return f"Pronto: {text}"


class FakeSpeaker:
    def __init__(self, failures=0):
        self.spoken = []
        self.chimes = 0
        self.played = 0
        self._failures = failures

    def chime(self):
        self.chimes += 1

    def synthesize(self, text):
        if self._failures:
            self._failures -= 1
            raise SynthesisError("sem voz")
        self.spoken.append(text)
        return AudioClip(np.array([0.1], np.float32), 22_050)

    def play(self, _clip):
        self.played += 1


def run_loop(
    frames, *, recorder=None, transcriber=None, speaker=None, assistant=None, **loop_options
):
    microphone = ScriptedMicrophone(frames)
    wake_word, assistant = FakeWakeWord(), assistant or FakeAssistant()
    speaker = speaker or FakeSpeaker()
    events = []
    loop = VoiceLoop(
        microphone=microphone,
        wake_word=wake_word,
        recorder=recorder or TwoFrameRecorder(),
        transcriber=transcriber or FakeTranscriber(),
        assistant=assistant,
        speaker=speaker,
        on_event=events.append,
        **loop_options,
    )
    loop.run(stop=None)
    return microphone, wake_word, assistant, speaker, events


def without_timing(events):
    return [event for event in events if not isinstance(event, Timed)]


def test_answers_a_request_that_follows_the_wake_word():
    microphone, wake_word, assistant, speaker, events = run_loop(
        [SILENCE, WAKE, SPEECH, SPEECH, SILENCE]
    )

    assert assistant.heard == ["acende a luz"]
    # A resposta inteira é falada, com o ponto final que a limpeza para fala acrescenta.
    assert speaker.spoken == ["Pronto: acende a luz."]
    assert speaker.chimes == 1
    assert without_timing(events) == [
        StateChanged(State.WAITING),
        StateChanged(State.LISTENING),
        StateChanged(State.TRANSCRIBING),
        Heard("acende a luz"),
        StateChanged(State.THINKING),
        Replied("Pronto: acende a luz"),
        StateChanged(State.SPEAKING),
        StateChanged(State.WAITING),
    ]
    assert sum(isinstance(event, Timed) for event in events) == 1
    # Depois de atender, esquece o próprio áudio: não deve se ativar sozinho nem ouvir a si mesmo.
    assert wake_word.resets == 1
    assert microphone.flushes == 2


def test_ignores_audio_without_the_wake_word():
    _, wake_word, assistant, speaker, events = run_loop([SILENCE, SPEECH, SILENCE])

    assert assistant.heard == []
    assert speaker.chimes == 0
    assert events == [StateChanged(State.WAITING)]
    assert wake_word.resets == 0


def test_goes_back_to_waiting_when_nobody_speaks_after_the_wake_word():
    _, wake_word, assistant, speaker, events = run_loop(
        [WAKE, SILENCE], recorder=TwoFrameRecorder(hears_speech=False)
    )

    assert assistant.heard == []
    assert speaker.spoken == []
    assert events[-1] == StateChanged(State.WAITING)
    assert not any(isinstance(event, Timed) for event in events)
    assert wake_word.resets == 1


def test_does_not_ask_the_assistant_about_empty_transcriptions():
    _, _, assistant, speaker, events = run_loop(
        [WAKE, SPEECH, SPEECH], transcriber=FakeTranscriber(text="")
    )

    assert assistant.heard == []
    assert speaker.spoken == []
    assert not any(isinstance(event, Heard) for event in events)


def test_a_failed_request_does_not_stop_the_loop():
    _, wake_word, assistant, speaker, _ = run_loop(
        [WAKE, SPEECH, SPEECH, WAKE, SPEECH, SPEECH], speaker=FakeSpeaker(failures=1)
    )

    assert assistant.heard == ["acende a luz", "acende a luz"]
    assert speaker.spoken == ["Pronto: acende a luz."]
    assert wake_word.resets == 2


def test_parts_can_be_replaced_between_requests():
    first, second = FakeAssistant(), FakeAssistant()
    microphone = ScriptedMicrophone([WAKE, SPEECH, SPEECH])
    loop = VoiceLoop(
        microphone=microphone,
        wake_word=FakeWakeWord(),
        recorder=TwoFrameRecorder(),
        transcriber=FakeTranscriber(),
        assistant=first,
        speaker=FakeSpeaker(),
    )

    loop.replace(assistant=second)
    loop.run(stop=None)

    assert first.heard == []
    assert second.heard == ["acende a luz"]


def test_unknown_parts_cannot_be_replaced():
    loop = VoiceLoop(
        microphone=ScriptedMicrophone([]),
        wake_word=FakeWakeWord(),
        recorder=TwoFrameRecorder(),
        transcriber=FakeTranscriber(),
        assistant=FakeAssistant(),
        speaker=FakeSpeaker(),
    )

    with pytest.raises(ValueError, match="on_event"):
        loop.replace(on_event=print)


def test_measures_the_microphone_level():
    loop = VoiceLoop(
        microphone=ScriptedMicrophone([np.full(4, 0.5, np.float32)]),
        wake_word=FakeWakeWord(),
        recorder=TwoFrameRecorder(),
        transcriber=FakeTranscriber(),
        assistant=FakeAssistant(),
        speaker=FakeSpeaker(),
    )

    loop.run(stop=None)

    assert loop.mic_level == pytest.approx(0.5)


def test_speaks_each_sentence_as_the_ai_writes_it():
    assistant = FakeAssistant(pieces=["Claro! Vou ", "ligar a luz. ", "Pronto"])

    _, _, _, speaker, events = run_loop([WAKE, SPEECH, SPEECH], assistant=assistant)

    assert assistant.received_callback == [True]
    assert speaker.spoken == ["Claro!", "Vou ligar a luz.", "Pronto."]
    assert Replied("Pronto: acende a luz") in events


def test_without_streaming_the_ai_is_not_asked_for_pieces():
    assistant = FakeAssistant(pieces=["Claro! "])

    _, _, _, speaker, _ = run_loop([WAKE, SPEECH, SPEECH], assistant=assistant, stream_speech=False)

    assert assistant.received_callback == [False]
    assert speaker.spoken == ["Pronto: acende a luz."]


def test_the_streaming_option_can_be_changed_while_running():
    assistant = FakeAssistant(pieces=["Oi. "])
    loop = VoiceLoop(
        microphone=ScriptedMicrophone([WAKE, SPEECH, SPEECH]),
        wake_word=FakeWakeWord(),
        recorder=TwoFrameRecorder(),
        transcriber=FakeTranscriber(),
        assistant=assistant,
        speaker=FakeSpeaker(),
    )

    loop.stream_speech = False
    loop.run(stop=None)

    assert assistant.received_callback == [False]


def test_reports_how_long_each_stage_took():
    clock = FakeClock()
    assistant = FakeAssistant(pieces=["Oi. "], clock=clock)

    _, _, _, _, events = run_loop(
        [WAKE, SPEECH, SPEECH],
        assistant=assistant,
        transcriber=FakeTranscriber(clock=clock, seconds=0.5),
        clock=clock,
    )

    (timed,) = [event for event in events if isinstance(event, Timed)]
    timing = timed.timing
    assert timing.transcription == 0.5
    # A IA demorou 1 s para escrever a primeira palavra e mais 1 s para terminar.
    assert timing.first_text == 1.0
    assert timing.reply == 2.0
    assert timing.first_sound is not None
    assert timing.total >= timing.reply


def test_the_timing_has_no_first_text_when_the_reply_does_not_stream():
    _, _, _, _, events = run_loop([WAKE, SPEECH, SPEECH], stream_speech=False)

    (timed,) = [event for event in events if isinstance(event, Timed)]
    assert timed.timing.first_text is None
    assert timed.timing.first_sound is not None


def test_a_reply_that_fails_midway_still_lets_the_speech_finish():
    class BrokenAssistant(FakeAssistant):
        def reply(self, text, on_text=None):
            on_text("Vou tentar. ")
            raise RuntimeError("a IA caiu")

    assistant = BrokenAssistant()

    _, wake_word, _, speaker, _ = run_loop([WAKE, SPEECH, SPEECH], assistant=assistant)

    assert speaker.spoken == ["Vou tentar."]
    assert wake_word.resets == 1
