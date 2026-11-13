"""Eventos do ciclo de voz, para a CLI e o painel mostrarem o que está acontecendo."""

from dataclasses import dataclass
from enum import StrEnum


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


Event = StateChanged | Heard | Replied
