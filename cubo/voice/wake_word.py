"""Detecção da palavra de ativação (wake word)."""

from pathlib import Path
from typing import Any

import numpy as np
from livekit.wakeword import WakeWordModel


class WakeWordDetector:
    def __init__(self, model_path: Path, threshold: float, *, model: Any = None) -> None:
        self._model = model if model is not None else WakeWordModel(models=[model_path])
        self._threshold = threshold

    def detected(self, frame: np.ndarray) -> bool:
        scores = self._model.predict(frame)
        return max(scores.values(), default=0.0) >= self._threshold

    def reset(self) -> None:
        """Esquece o áudio já ouvido, para a mesma fala não disparar duas vezes."""
        self._model.reset()
