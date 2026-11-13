"""Formato de áudio interno do Cubô: float32 mono em [-1, 1], a 16 kHz, em quadros de 80 ms."""

from dataclasses import dataclass

import numpy as np
import soxr

SAMPLE_RATE = 16_000  # taxa usada pela wake word, pelo VAD e pelo Whisper
FRAME_SAMPLES = 1_280  # 80 ms, o passo da wake word


@dataclass(frozen=True)
class AudioClip:
    samples: np.ndarray  # float32 mono em [-1, 1]
    sample_rate: int


def to_float32(samples: np.ndarray) -> np.ndarray:
    """Converte PCM int16 ou float para float32 em [-1, 1]."""
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    return np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)


class StreamResampler:
    """Converte blocos contínuos do microfone para 16 kHz.

    Trabalha em float32 e limita o resultado a [-1, 1], então picos não dão a volta
    como acontecia na conversão direta para int16.
    """

    def __init__(self, input_rate: int) -> None:
        self._stream = (
            soxr.ResampleStream(input_rate, SAMPLE_RATE, 1, dtype="float32")
            if input_rate != SAMPLE_RATE
            else None
        )

    def __call__(self, block: np.ndarray) -> np.ndarray:
        samples = to_float32(block)
        if self._stream is not None:
            samples = self._stream.resample_chunk(samples)
        return np.clip(samples, -1.0, 1.0)


class FrameBuffer:
    """Junta blocos de tamanhos variados em quadros de tamanho fixo."""

    def __init__(self, frame_samples: int = FRAME_SAMPLES) -> None:
        self._frame_samples = frame_samples
        self._pending = np.zeros(0, np.float32)

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._pending = np.concatenate([self._pending, samples])
        count = len(self._pending) // self._frame_samples
        size = self._frame_samples
        frames = [self._pending[index * size : (index + 1) * size] for index in range(count)]
        self._pending = self._pending[count * size :]
        return frames

    def clear(self) -> None:
        self._pending = np.zeros(0, np.float32)


def resample(clip: AudioClip, sample_rate: int) -> AudioClip:
    """Muda a taxa de amostragem de um trecho inteiro, como uma fala sintetizada."""
    if clip.sample_rate == sample_rate:
        return clip
    samples = soxr.resample(clip.samples, clip.sample_rate, sample_rate)
    return AudioClip(np.clip(samples, -1.0, 1.0).astype(np.float32), sample_rate)


def chime(frequency: float = 880.0, seconds: float = 0.12, volume: float = 0.3) -> AudioClip:
    """Bipe curto que avisa que o Cubô ouviu a wake word e está escutando."""
    time = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * frequency * time) * volume
    # Entrada e saída suaves de 10 ms, para o bipe não estalar.
    fade = np.minimum(1.0, np.minimum(time, time[::-1]) / 0.01)
    return AudioClip((tone * fade).astype(np.float32), SAMPLE_RATE)
