import io
import subprocess
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from cubo.voice.audio import SAMPLE_RATE, AudioClip
from cubo.voice.tts import EspeakSynthesizer, PiperSynthesizer, Speaker, SynthesisError


class FakePiperVoice:
    def __init__(self, chunks):
        self._chunks = chunks
        self.configs = []

    def synthesize(self, text, config):
        self.configs.append(config)
        return iter(self._chunks)


def chunk(values, sample_rate=22_050):
    return SimpleNamespace(audio_float_array=np.array(values, np.float32), sample_rate=sample_rate)


def test_piper_joins_the_chunks_into_one_clip(tmp_path):
    voice = FakePiperVoice([chunk([0.1, 0.2]), chunk([0.3])])

    clip = PiperSynthesizer(tmp_path / "voz.onnx", voice=voice).synthesize("Olá")

    assert clip.samples.tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert clip.sample_rate == 22_050


@pytest.mark.parametrize("speed, length_scale", [(1.0, 1.0), (2.0, 0.5), (0.5, 2.0)])
def test_piper_speed_is_the_inverse_of_length_scale(tmp_path, speed, length_scale):
    voice = FakePiperVoice([chunk([0.1])])

    PiperSynthesizer(tmp_path / "voz.onnx", speed=speed, voice=voice).synthesize("Olá")

    assert voice.configs[0].length_scale == pytest.approx(length_scale)


def test_piper_without_audio_gives_an_empty_clip(tmp_path):
    clip = PiperSynthesizer(tmp_path / "voz.onnx", voice=FakePiperVoice([])).synthesize("...")

    assert len(clip.samples) == 0


def wav_bytes(samples, *, rate=22_050, width=2, channels=1, streamed=False) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(np.array(samples, np.int16).tobytes())
    content = bytearray(buffer.getvalue())
    if streamed:
        # Pela saída padrão o espeak-ng não sabe o tamanho final: o cabeçalho traz um valor máximo.
        content[4:8] = (0x7FFFFFFF).to_bytes(4, "little")
        content[40:44] = (0x7FFFFFFF).to_bytes(4, "little")
    return bytes(content)


class FakeEspeak:
    def __init__(self, output=b"", error=None):
        self._output = output
        self._error = error
        self.calls = []

    def __call__(self, command, **options):
        self.calls.append((command, options))
        if self._error:
            raise self._error
        return subprocess.CompletedProcess(command, 0, stdout=self._output)


@pytest.mark.parametrize("streamed", [False, True])
def test_espeak_reads_the_wav_it_prints(streamed):
    run = FakeEspeak(wav_bytes([0, 16384, -32768], streamed=streamed))

    clip = EspeakSynthesizer(run=run).synthesize("Olá")

    assert clip.samples.tolist() == [0.0, 0.5, -1.0]
    assert clip.sample_rate == 22_050


def test_espeak_gets_the_text_by_stdin_in_portuguese():
    run = FakeEspeak(wav_bytes([0]))

    EspeakSynthesizer(speed=1.5, run=run).synthesize("-oi")

    command, options = run.calls[0]
    assert command[:3] == ["espeak-ng", "-v", "pt-br"]
    assert command[command.index("-s") + 1] == "240"
    assert "-oi" not in command
    assert options["input"] == b"-oi"


@pytest.mark.parametrize(
    "error", [FileNotFoundError("espeak-ng"), subprocess.CalledProcessError(1, "espeak-ng")]
)
def test_espeak_failure_becomes_a_synthesis_error(error):
    with pytest.raises(SynthesisError, match="espeak-ng"):
        EspeakSynthesizer(run=FakeEspeak(error=error)).synthesize("Olá")


def test_espeak_unexpected_format_is_rejected():
    with pytest.raises(SynthesisError, match="formato"):
        EspeakSynthesizer(run=FakeEspeak(wav_bytes([0, 0], channels=2))).synthesize("Olá")


class RecordingPlayer:
    def __init__(self):
        self.clips = []

    def play(self, clip):
        self.clips.append(clip)


class FixedSynthesizer:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return AudioClip(np.array([0.1], np.float32), 22_050)


def test_speaker_synthesizes_and_plays():
    synthesizer, player = FixedSynthesizer(), RecordingPlayer()

    Speaker(synthesizer, player).say("Olá")

    assert synthesizer.texts == ["Olá"]
    assert player.clips[0].sample_rate == 22_050


@pytest.mark.parametrize("text", ["", "   "])
def test_speaker_ignores_empty_text(text):
    synthesizer, player = FixedSynthesizer(), RecordingPlayer()

    Speaker(synthesizer, player).say(text)

    assert synthesizer.texts == []
    assert player.clips == []


def test_speaker_chime_plays_without_synthesizing():
    synthesizer, player = FixedSynthesizer(), RecordingPlayer()

    Speaker(synthesizer, player).chime()

    assert synthesizer.texts == []
    assert player.clips[0].sample_rate == SAMPLE_RATE
    assert len(player.clips[0].samples) > 0
