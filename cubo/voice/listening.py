"""Escuta do pedido: grava enquanto a pessoa fala e para quando ela fica em silêncio."""

import math
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np
from faster_whisper.vad import get_vad_model

from cubo.voice.audio import SAMPLE_RATE

VAD_WINDOW_SAMPLES = 512  # 32 ms, a janela do Silero VAD
VAD_CONTEXT_WINDOWS = 16  # cerca de 0,5 s de contexto em cada avaliação


class SpeechDetector:
    """Diz se há voz no quadro, usando o Silero VAD que já vem com o faster-whisper."""

    def __init__(self, threshold: float = 0.5, *, model: Any = None) -> None:
        self._model = model if model is not None else get_vad_model()
        self._threshold = threshold
        self._recent = np.zeros(0, np.float32)

    def is_speech(self, frame: np.ndarray) -> bool:
        self._recent = np.concatenate([self._recent, frame])[
            -VAD_WINDOW_SAMPLES * VAD_CONTEXT_WINDOWS :
        ]
        usable = len(self._recent) - len(self._recent) % VAD_WINDOW_SAMPLES
        if usable == 0:
            return False
        probabilities = np.asarray(self._model(self._recent[-usable:])).reshape(-1)
        # Só as janelas que cobrem o quadro novo decidem.
        newest = probabilities[-math.ceil(len(frame) / VAD_WINDOW_SAMPLES) :]
        return float(newest.max()) >= self._threshold

    def reset(self) -> None:
        self._recent = np.zeros(0, np.float32)


@dataclass(frozen=True)
class ListeningLimits:
    silence_seconds: float = 0.8  # silêncio que encerra o pedido
    max_seconds: float = 15.0  # duração máxima de um pedido
    wait_seconds: float = 5.0  # tempo esperando a pessoa começar a falar


class UtteranceRecorder:
    def __init__(self, detector: SpeechDetector, limits: ListeningLimits) -> None:
        self._detector = detector
        self._limits = limits

    def record(self, frames: Iterator[np.ndarray]) -> np.ndarray | None:
        """Grava um pedido. Retorna ``None`` se ninguém falar a tempo."""
        self._detector.reset()
        collected: list[np.ndarray] = []
        heard_speech = False
        silence = elapsed = 0.0
        for frame in frames:
            collected.append(frame)
            duration = len(frame) / SAMPLE_RATE
            elapsed += duration
            if self._detector.is_speech(frame):
                heard_speech, silence = True, 0.0
            else:
                silence += duration
            if heard_speech and silence >= self._limits.silence_seconds:
                break
            if not heard_speech and elapsed >= self._limits.wait_seconds:
                return None
            if elapsed >= self._limits.max_seconds:
                break
        return np.concatenate(collected) if heard_speech else None
