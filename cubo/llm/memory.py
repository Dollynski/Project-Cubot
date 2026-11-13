"""Memória da conversa: guarda as últimas trocas e esquece tudo depois de um tempo parado."""

import time
from collections import deque
from collections.abc import Callable

from cubo.llm.base import Exchange


class ConversationMemory:
    def __init__(
        self,
        *,
        max_exchanges: int,
        idle_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._exchanges: deque[Exchange] = deque(maxlen=max_exchanges)
        self._idle_timeout = idle_timeout_seconds
        self._clock = clock
        self._last_activity: float | None = None

    def history(self) -> tuple[Exchange, ...]:
        """As trocas guardadas, da mais antiga para a mais nova. Vazio se a conversa esfriou."""
        if self._is_idle():
            self.clear()
        return tuple(self._exchanges)

    def add(self, exchange: Exchange) -> None:
        self._exchanges.append(exchange)
        self._last_activity = self._clock()

    def clear(self) -> None:
        self._exchanges.clear()
        self._last_activity = None

    def _is_idle(self) -> bool:
        if self._last_activity is None:
            return False
        return self._clock() - self._last_activity > self._idle_timeout
