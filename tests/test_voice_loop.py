import numpy as np

from cubo.voice.events import Heard, Replied, State, StateChanged
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


class FakeTranscriber:
    def __init__(self, text="acende a luz"):
        self._text = text

    def transcribe(self, _audio):
        return self._text


class FakeAssistant:
    def __init__(self):
        self.heard = []

    def reply(self, text):
        self.heard.append(text)
        return f"Pronto: {text}"


class FakeSpeaker:
    def __init__(self, failures=0):
        self.spoken = []
        self.chimes = 0
        self._failures = failures

    def chime(self):
        self.chimes += 1

    def say(self, text):
        if self._failures:
            self._failures -= 1
            raise SynthesisError("sem voz")
        self.spoken.append(text)


def run_loop(frames, *, recorder=None, transcriber=None, speaker=None):
    microphone = ScriptedMicrophone(frames)
    wake_word, assistant = FakeWakeWord(), FakeAssistant()
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
    )
    loop.run(stop=None)
    return microphone, wake_word, assistant, speaker, events


def test_answers_a_request_that_follows_the_wake_word():
    microphone, wake_word, assistant, speaker, events = run_loop(
        [SILENCE, WAKE, SPEECH, SPEECH, SILENCE]
    )

    assert assistant.heard == ["acende a luz"]
    assert speaker.spoken == ["Pronto: acende a luz"]
    assert speaker.chimes == 1
    assert events == [
        StateChanged(State.WAITING),
        StateChanged(State.LISTENING),
        StateChanged(State.TRANSCRIBING),
        Heard("acende a luz"),
        StateChanged(State.THINKING),
        Replied("Pronto: acende a luz"),
        StateChanged(State.SPEAKING),
        StateChanged(State.WAITING),
    ]
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
    assert speaker.spoken == ["Pronto: acende a luz"]
    assert wake_word.resets == 2
