"""Fala do Cubô: síntese de voz (Piper, ou espeak-ng como reserva) e reprodução."""

import io
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from piper import PiperVoice, SynthesisConfig

from cubo.voice.audio import SAMPLE_RATE, AudioClip, chime, to_float32

ESPEAK_BASE_WORDS_PER_MINUTE = 160


class SynthesisError(Exception):
    """Não foi possível transformar o texto em fala."""


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> AudioClip: ...


class Player(Protocol):
    def play(self, clip: AudioClip) -> None:
        """Toca o trecho e só retorna quando ele terminar."""
        ...


class PiperSynthesizer:
    """Voz neural local, bem mais natural que o espeak-ng."""

    def __init__(self, voice_path: Path, *, speed: float = 1.0, voice: Any = None) -> None:
        self._voice = voice if voice is not None else PiperVoice.load(voice_path)
        # No Piper, quanto maior o length_scale, mais lenta a fala.
        self._config = SynthesisConfig(length_scale=1.0 / speed)

    def synthesize(self, text: str) -> AudioClip:
        chunks = list(self._voice.synthesize(text, self._config))
        if not chunks:
            return AudioClip(np.zeros(0, np.float32), SAMPLE_RATE)
        samples = np.concatenate([chunk.audio_float_array for chunk in chunks])
        return AudioClip(to_float32(samples), chunks[0].sample_rate)


class EspeakSynthesizer:
    """Voz robótica, mas que não precisa baixar nada: serve de reserva."""

    def __init__(
        self,
        *,
        speed: float = 1.0,
        run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        self._words_per_minute = round(ESPEAK_BASE_WORDS_PER_MINUTE * speed)
        self._run = run

    def synthesize(self, text: str) -> AudioClip:
        command = ["espeak-ng", "-v", "pt-br", "-s", str(self._words_per_minute), "--stdout"]
        try:
            # O texto vai pela entrada padrão: assim um "-" no começo não vira opção.
            result = self._run(command, input=text.encode(), capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise SynthesisError(f"O espeak-ng falhou: {error}") from error
        return _read_wav(result.stdout)


def _read_wav(content: bytes) -> AudioClip:
    with wave.open(io.BytesIO(content)) as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise SynthesisError("O espeak-ng devolveu um áudio em formato inesperado.")
        # Pela saída padrão o cabeçalho não traz o tamanho real, então lê o que houver.
        frames = wav.readframes(wav.getnframes())
        sample_rate = wav.getframerate()
    return AudioClip(to_float32(np.frombuffer(frames, dtype=np.int16)), sample_rate)


class Speaker:
    def __init__(self, synthesizer: Synthesizer, player: Player) -> None:
        self._synthesizer = synthesizer
        self._player = player
        self._chime = chime()

    def synthesize(self, text: str) -> AudioClip:
        return self._synthesizer.synthesize(text)

    def play(self, clip: AudioClip) -> None:
        """Toca o trecho e só retorna quando ele terminar."""
        self._player.play(clip)

    def say(self, text: str) -> None:
        if text.strip():
            self.play(self.synthesize(text))

    def chime(self) -> None:
        self._player.play(self._chime)
