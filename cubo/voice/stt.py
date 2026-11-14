"""Transcrição da fala com o faster-whisper, carregado uma vez e mantido na memória."""

from pathlib import Path
from typing import Any

import numpy as np
from faster_whisper import WhisperModel

from cubo.voice.audio import SAMPLE_RATE

# Acima disso, o próprio Whisper acha que o trecho não tem fala (evita frases inventadas).
NO_SPEECH_LIMIT = 0.6


class Transcriber:
    def __init__(
        self,
        model_name: str,
        compute_type: str,
        download_root: Path,
        *,
        model: Any = None,
    ) -> None:
        self._model = model or WhisperModel(
            model_name,
            device="cpu",
            compute_type=compute_type,
            download_root=str(download_root),
            # Nada é baixado durante o uso: os modelos vêm do `cubo preparar`.
            local_files_only=True,
        )

    def warm_up(self) -> None:
        """Transcreve um segundo de silêncio, para o primeiro pedido não pagar a inicialização."""
        self.transcribe(np.zeros(SAMPLE_RATE, np.float32))

    def transcribe(self, audio: np.ndarray) -> str:
        """Recebe float32 mono a 16 kHz e devolve o texto completo, juntando todos os trechos."""
        segments, _info = self._model.transcribe(
            audio,
            language="pt",
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=False,
            # Sem as repetições com temperatura maior: num áudio ruim elas multiplicam o tempo de
            # transcrição (de 0,5 s para vários segundos) e costumam piorar o texto.
            temperature=0.0,
        )
        # `segments` é um gerador: a transcrição só acontece de fato ao percorrê-lo.
        spoken = [
            segment.text.strip() for segment in segments if segment.no_speech_prob < NO_SPEECH_LIMIT
        ]
        return " ".join(text for text in spoken if text)
