import threading
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
from cubo.voice.tts import WARM_UP_TEXT

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
        self.wake_words = []
        self.transcribers = []
        self.detectors = []
        self.transcriber_error = None
        monkeypatch.setattr(session_module, "load_wake_word", self._wake_word)
        monkeypatch.setattr(session_module, "load_transcriber", self._transcriber)
        monkeypatch.setattr(session_module, "load_synthesizer", self._synthesizer)
        monkeypatch.setattr(session_module, "SpeechDetector", self._detector)
        monkeypatch.setattr(session_module, "load_devices", self._devices)

    def _wake_word(self, settings, _data_dir):
        self.calls.append("wake_word")
        self.wake_words.append(FakeWakeWord())
        return self.wake_words[-1]

    def _detector(self):
        self.detectors.append(FakeDetector())
        return self.detectors[-1]

    def _transcriber(self, settings, _data_dir):
        self.calls.append("transcriber")
        if self.transcriber_error:
            raise self.transcriber_error
        self.transcribers.append(FakeTranscriber())
        return self.transcribers[-1]

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
    def __init__(self):
        self.warm_ups = 0

    def detected(self, _frame):
        return False

    def reset(self):
        pass

    def warm_up(self):
        self.warm_ups += 1


class FakeTranscriber:
    def __init__(self):
        self.warm_ups = 0
        self.warm_up_error = None

    def warm_up(self):
        if self.warm_up_error:
            raise self.warm_up_error
        self.warm_ups += 1


class FakeDetector:
    def __init__(self):
        self.warm_ups = 0

    def warm_up(self):
        self.warm_ups += 1


def spoken(synthesizer):
    """O que foi pedido ao sintetizador, sem o aquecimento."""
    return [text for text in synthesizer.texts if text != WARM_UP_TEXT]


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
    assert spoken(loaders.synthesizers[0]) == []
    assert spoken(loaders.synthesizers[1]) == ["oi"]


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
    assert spoken(loaders.synthesizers[0]) == ["oi"]


def test_a_failed_reload_leaves_the_session_as_it_was(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.transcriber_error = SetupError("modelo ausente")

    with pytest.raises(SetupError, match="modelo ausente"):
        session.reconfigure(VoiceSettings(whisper_model="small", speech_speed=1.5))

    assert session.settings == VoiceSettings()
    session.say("oi")
    assert spoken(loaders.synthesizers[0]) == ["oi"]


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


def test_every_model_is_warmed_up_before_the_first_request(loaders, tmp_path):
    make_session(tmp_path)

    assert loaders.wake_words[0].warm_ups == 1
    assert loaders.transcribers[0].warm_ups == 1
    assert loaders.detectors[0].warm_ups == 1
    assert loaders.synthesizers[0].texts == [WARM_UP_TEXT]


def test_reconfigure_warms_up_only_the_new_part(loaders, tmp_path):
    session = make_session(tmp_path)

    session.reconfigure(VoiceSettings(speech_speed=1.5))

    assert loaders.synthesizers[1].texts == [WARM_UP_TEXT]
    assert loaders.transcribers[0].warm_ups == 1
    assert loaders.wake_words[0].warm_ups == 1
    assert len(loaders.transcribers) == 1


def test_a_new_model_that_fails_to_warm_up_leaves_the_session_as_it_was(
    loaders, monkeypatch, tmp_path
):
    session = make_session(tmp_path)
    original_load = loaders._transcriber

    def broken_transcriber(settings, data_dir):
        transcriber = original_load(settings, data_dir)
        transcriber.warm_up_error = RuntimeError("modelo corrompido")
        return transcriber

    monkeypatch.setattr(session_module, "load_transcriber", broken_transcriber)

    with pytest.raises(RuntimeError, match="corrompido"):
        session.reconfigure(VoiceSettings(whisper_model="small", speech_speed=1.5))

    assert session.settings == VoiceSettings()
    session.say("oi")
    assert spoken(loaders.synthesizers[0]) == ["oi"]


def test_the_streaming_option_comes_from_the_settings(loaders, tmp_path):
    session = make_session(tmp_path, stream_speech=False)

    assert session._loop.stream_speech is False


def test_the_streaming_option_changes_without_reloading_anything(loaders, tmp_path):
    session = make_session(tmp_path)
    loaders.calls.clear()

    changed = session.reconfigure(VoiceSettings(stream_speech=False))

    assert changed == []
    assert loaders.calls == []
    assert session._loop.stream_speech is False
    assert session.settings.stream_speech is False


class SlowMicrophone(FakeMicrophone):
    """Só para de escutar quando liberado: faz de conta que está no meio de um pedido longo."""

    def __init__(self, device, release):
        super().__init__(device)
        self.release = release

    def frames(self, stop):
        while not self.release.is_set():
            self.release.wait(0.005)
        return
        yield


def start_with_a_busy_microphone(loaders, tmp_path, monkeypatch, *, stop_wait, swap_wait):
    """Sessão ligada, com um pedido longo em andamento que o teste libera quando quiser."""
    monkeypatch.setattr(session_module, "STOP_TIMEOUT_SECONDS", stop_wait)
    monkeypatch.setattr(session_module, "SWAP_WAIT_SECONDS", swap_wait)
    release = threading.Event()
    session = make_session(tmp_path)
    busy = SlowMicrophone(None, release)
    session._microphone = busy
    session._loop.replace(microphone=busy)
    session.start()
    return session, busy, release


def test_swapping_the_microphone_waits_for_the_request_in_progress(loaders, monkeypatch, tmp_path):
    session, old, release = start_with_a_busy_microphone(
        loaders, tmp_path, monkeypatch, stop_wait=0.05, swap_wait=5.0
    )
    threading.Timer(0.3, release.set).start()

    changed = session.reconfigure(VoiceSettings(input_device="USB"))

    new = loaders.microphones[-1]
    assert changed == ["microfone"]
    assert old.closed == 1
    # O microfone novo não pode ser fechado pela thread antiga ao terminar.
    assert (new.opened, new.closed) == (1, 0)
    assert session.running
    session.stop()
    assert new.closed == 1


def test_a_request_that_never_ends_leaves_the_session_unchanged(loaders, monkeypatch, tmp_path):
    session, old, release = start_with_a_busy_microphone(
        loaders, tmp_path, monkeypatch, stop_wait=0.02, swap_wait=0.05
    )

    try:
        with pytest.raises(SetupError, match="terminando um pedido"):
            session.reconfigure(VoiceSettings(input_device="USB", speech_speed=1.5))

        assert session.settings == VoiceSettings()
        session.say("oi")
        assert spoken(loaders.synthesizers[0]) == ["oi"]
        assert session._microphone is old
    finally:
        release.set()


def test_a_new_microphone_that_does_not_open_brings_the_old_one_back(
    loaders, monkeypatch, tmp_path
):
    session = make_session(tmp_path)
    session.start()
    old = loaders.microphones[0]
    original_microphone = loaders._devices().Microphone

    def broken_open():
        raise SetupError("Não consegui abrir o microfone")

    def make_broken(device):
        microphone = original_microphone(device)
        microphone.open = broken_open
        return microphone

    monkeypatch.setattr(
        session_module,
        "load_devices",
        lambda: SimpleNamespace(
            Microphone=make_broken, SoundDevicePlayer=loaders._devices().SoundDevicePlayer
        ),
    )
    try:
        with pytest.raises(SetupError, match="abrir o microfone"):
            session.reconfigure(VoiceSettings(input_device="USB"))

        assert session.settings == VoiceSettings()
        assert session._microphone is old
        assert session.running
        assert old.opened == 2  # voltou a escutar pelo antigo
    finally:
        session.stop()
