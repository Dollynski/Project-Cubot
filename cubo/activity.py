"""O que o Cubô está fazendo e o que foi dito nas últimas conversas, para o painel mostrar."""

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from cubo.voice.events import Event, Heard, Replied, State, StateChanged


@dataclass(frozen=True)
class Entry:
    time: datetime
    author: Literal["you", "cubo"]
    text: str


class ActivityLog:
    """Recebe os eventos do ciclo de voz e guarda o estado atual e o histórico recente."""

    def __init__(self, max_entries: int = 50) -> None:
        self._entries: deque[Entry] = deque(maxlen=max_entries)
        self._state = State.WAITING
        self._lock = threading.Lock()

    def record(self, event: Event) -> None:
        with self._lock:
            match event:
                case StateChanged(state):
                    self._state = state
                case Heard(text):
                    self._entries.append(Entry(datetime.now(), "you", text))
                case Replied(text) if text:
                    self._entries.append(Entry(datetime.now(), "cubo", text))

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    def entries(self) -> list[Entry]:
        """Do mais antigo para o mais novo."""
        with self._lock:
            return list(self._entries)
