import time
from types import SimpleNamespace

import numpy as np
import pytest

from cubo.config import VoiceSettings
from cubo.errors import SetupError
from cubo.voice import session as session_module
from cubo.voice.audio import AudioClip
from cubo.voice.listening import ListeningLimits
from cubo.voice.session import VoiceSession

SILENCE = np.zeros(1280, np.float32)


class FakeMicrophone:
    def __init__(self, device):
        self.device = device
        self.opened = 0
        self.closed = 0

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1

    def flush(self):
        pass

    def frames(self, stop):
        while not stop.is_set():
            stop.wait(0.005)
        return
        yield


class FakePlayer:
    def __init__(self, device):
        self.device = device
        self.clips = []

    def play(self, clip):
        self.clips.append(clip)


class FakeSynthesizer:
    def __init__(self, name):
        self.name = name
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return AudioClip(np.array([0.1], np.float32), 22_050)


class Loaders:
    """Troca os carregadores de modelos e o PortAudio por fakes que anotam cada chamada."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.synthesizers = []
        self.microphones = []
        self.players = []
        self.wake_word_error = None
        self.transcriber_error = None
        monkeypatch.setattr(session_module, "load_wake_word", self._wake_word)
        monkeypatch.setattr(session_module, "load_transcriber", self._transcriber)
        monkeypatch.setattr(session_module, "load_synthesizer", self._synthesizer)
        monkeypatch.setattr(session_module, "SpeechDetector", lambda: "vad")
        monkeypatch.setattr(session_module, "load_devices", self._devices)

    def _wake_word(self, settings, _data_dir):
        self.calls.append("wake_word")
        return FakeWakeWord()

    def _transcriber(self, settings, _data_dir):
        self.calls.append("transcriber")
        if self.transcriber_error:
            raise self.transcriber_error
        return "stt"

    def _synthesizer(self, settings, _data_dir, _warnings):
        self.calls.append("synthesizer")
        synthesizer = FakeSynthesizer(f"voz {settings.piper_voice} x{settings.speech_speed}")
        self.synthesizers.append(synthesizer)
        return synthesizer

    def _devices(self):
        def microphone(device):
            fake = FakeMicrophone(device)
            self.microphones.append(fake)
            return fake

        def player(device):
            fake = FakePlayer(device)
            self.players.append(fake)
            return fake

        return SimpleNamespace(Microphone=microphone, SoundDevicePlayer=player)


class FakeWakeWord:
    crash = None

    def detected(self, _frame):
        return False

    def reset(self):
        pass


@pytest.fixture
def loaders(monkeypatch):
    return Loaders(monkeypatch)


def make_session(tmp_path, **settings):
    return VoiceSession(VoiceSettings(**settings), assistant="assistente", data_dir=tmp_path)


def wait_until(condition, timeout=2.0):
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        time.sleep(0.005)
    return condition()


def test_start_and_stop_run_the_loop_in_a_thread(loaders, tmp_path):
    session = make_session(tmp_path)

    session.start()
    assert session.running
    assert loaders.microphones[0].opened == 1

    session.stop()
    assert not session.running
    assert loaders.microphones[0].closed == 1


def test_devices_come_from_the_settings(loaders, tmp_path):
    make_session(tmp_path, input_device="2", output_device="Caixa")

    assert loaders.microphones[0].device == 2
    assert loaders.players[0].device == "Caixa"


def test_start_twice_does_not_open_the_microphone_twice(loaders, tmp_path):
    session = make_session(tmp_path)

    session.start()
    session.start()
    session.stop()

    assert loaders.microphones[0].opened == 1


def test_a_microphone_that_does_not_open_is_a_setup_error(loaders, tmp_path):
    session = make_session(tmp_path)

    def broken_open():
        raise SetupError("Não consegui abrir o microfone")

    loaders.microphones[0].open = broken_open

    with pytest.raises(SetupError, match="microfone"):
        session.start()
    assert not session.running


def test_reconfigure_without_changes_touches_nothing(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.calls.clear()

    assert session.reconfigure(VoiceSettings()) == []

    assert loaders.calls == []


def test_reconfigure_reloads_only_the_part_that_changed(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.calls.clear()

    changed = session.reconfigure(VoiceSettings(speech_speed=1.5))

    assert changed == ["voz"]
    assert loaders.calls == ["synthesizer"]
    session.say("oi")
    assert loaders.synthesizers[0].texts == []
    assert loaders.synthesizers[1].texts == ["oi"]


def test_reconfigure_reports_every_part_in_a_fixed_order(loaders, tmp_path):
    session = make_session(tmp_path)

    changed = session.reconfigure(
        VoiceSettings(whisper_model="small", wake_word_threshold=0.7, silence_seconds=1.0)
    )

    assert changed == ["palavra de ativação", "transcrição", "gravação"]


def test_new_output_device_keeps_the_current_voice(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.calls.clear()

    assert session.reconfigure(VoiceSettings(output_device="Fone")) == ["alto-falante"]

    assert loaders.calls == []
    session.say("oi")
    assert loaders.players[1].device == "Fone"
    assert len(loaders.players[1].clips) == 1
    assert loaders.synthesizers[0].texts == ["oi"]


def test_a_failed_reload_leaves_the_session_as_it_was(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.transcriber_error = SetupError("modelo ausente")

    with pytest.raises(SetupError, match="modelo ausente"):
        session.reconfigure(VoiceSettings(whisper_model="small", speech_speed=1.5))

    assert session.settings == VoiceSettings()
    session.say("oi")
    assert loaders.synthesizers[0].texts == ["oi"]


def test_changing_the_microphone_restarts_the_listening(loaders, tmp_path):
    session = make_session(tmp_path)
    session.start()

    assert session.reconfigure(VoiceSettings(input_device="USB")) == ["microfone"]

    old, new = loaders.microphones
    assert (old.opened, old.closed) == (1, 1)
    assert new.device == "USB"
    assert new.opened == 1
    assert session.running
    session.stop()


def test_changing_the_microphone_while_stopped_does_not_start_it(loaders, tmp_path):
    session = make_session(tmp_path)

    session.reconfigure(VoiceSettings(input_device="USB"))

    assert not session.running
    assert loaders.microphones[1].opened == 0


def test_a_crash_in_the_loop_is_reported_and_releases_the_microphone(loaders, tmp_path):
    session = make_session(tmp_path)

    class CrashingMicrophone(FakeMicrophone):
        def frames(self, stop):
            raise RuntimeError("placa de som sumiu")
            yield

    crashing = CrashingMicrophone(None)
    session._loop.replace(microphone=crashing)
    session._microphone = crashing

    session.start()

    assert wait_until(lambda: not session.running)
    assert session.error == "placa de som sumiu"
    assert crashing.closed == 1


def test_limits_come_from_the_settings(loaders, monkeypatch, tmp_path):
    created = []
    monkeypatch.setattr(
        session_module, "UtteranceRecorder", lambda detector, limits: created.append(limits)
    )

    session = make_session(tmp_path, silence_seconds=1.2, max_listening_seconds=9)
    session.reconfigure(VoiceSettings(silence_seconds=2.0, max_listening_seconds=9))

    assert created == [
        ListeningLimits(silence_seconds=1.2, max_seconds=9),
        ListeningLimits(silence_seconds=2.0, max_seconds=9),
    ]


def test_stop_without_start_is_harmless(loaders, tmp_path):
    session = make_session(tmp_path)

    session.stop()

    assert not session.running
