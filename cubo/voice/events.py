"""Eventos do ciclo de voz, para a CLI e o painel mostrarem o que está acontecendo."""

from dataclasses import dataclass
from enum import StrEnum

from cubo.voice.timing import Timing


class State(StrEnum):
    WAITING = "aguardando"
    LISTENING = "ouvindo"
    TRANSCRIBING = "transcrevendo"
    THINKING = "pensando"
    SPEAKING = "falando"


@dataclass(frozen=True)
class StateChanged:
    state: State


@dataclass(frozen=True)
class Heard:
    text: str


@dataclass(frozen=True)
class Replied:
    text: str


@dataclass(frozen=True)
class Timed:
    """Quanto cada etapa do pedido que acabou de terminar demorou."""

    timing: Timing


Event = StateChanged | Heard | Replied | Timed
