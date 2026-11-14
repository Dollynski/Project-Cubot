"""Medição de quanto cada etapa de um pedido demora, para saber onde está o tempo."""

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Timing:
    """Tempos de um pedido, em segundos. Os de espera contam a partir do fim da gravação."""

    transcription: float  # converter a fala em texto
    first_text: float | None  # até a IA começar a responder (None se ela não escreveu nada)
    reply: float  # até a IA terminar de responder
    first_sound: float | None  # até o Cubô começar a falar: o que a pessoa sente de espera
    total: float  # até terminar de falar


class Stopwatch:
    """Cronômetro de um pedido: anota quando cada etapa aconteceu, a partir do início."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._start = clock()
        self._marks: dict[str, float] = {}

    def mark(self, name: str) -> None:
        """Anota o instante da etapa. Só a primeira vez conta ("primeira palavra", por exemplo)."""
        self._marks.setdefault(name, self._clock() - self._start)

    def at(self, name: str) -> float | None:
        return self._marks.get(name)

    def timing(self) -> Timing:
        transcribed = self._marks.get("transcribed", 0.0)
        reply = self._marks.get("replied", transcribed)
        first_text = self._marks.get("first_text")
        return Timing(
            transcription=transcribed,
            first_text=None if first_text is None else first_text - transcribed,
            reply=reply - transcribed,
            first_sound=self._marks.get("first_sound"),
            total=self._marks.get("done", reply),
        )
