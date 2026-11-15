"""Uso da IA: limite de chamadas por minuto e por dia, e contador de tokens."""

import fcntl
import threading
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cubo.llm.base import ProviderError, Usage
from cubo.toml_files import read_toml, write_toml

USAGE_FILE_NAME = "usage.toml"


@dataclass(frozen=True)
class UsageSnapshot:
    calls_last_minute: int
    calls_today: int
    input_tokens_today: int
    output_tokens_today: int
    max_calls_per_minute: int  # zero é sem limite
    max_calls_per_day: int


class UsageTracker:
    """Controla quantas chamadas à IA foram feitas e quantos tokens elas gastaram.

    O total do dia fica num arquivo compartilhado: vale também depois de reiniciar e soma o que
    outros processos do Cubô (como o modo texto rodando junto com o serviço) fizeram no dia. O
    limite por minuto, ao contrário, é de cada processo.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        max_calls_per_minute: int = 0,
        max_calls_per_day: int = 0,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: deque[datetime] = deque()
        self._max_per_minute = max_calls_per_minute
        self._max_per_day = max_calls_per_day
        self._day = clock().date()
        self._calls = self._input_tokens = self._output_tokens = 0
        self._sync(clock())

    def set_limits(self, *, max_calls_per_minute: int, max_calls_per_day: int) -> None:
        with self._lock:
            self._max_per_minute = max_calls_per_minute
            self._max_per_day = max_calls_per_day

    def acquire(self) -> None:
        """Registra uma chamada. Levanta ``ProviderError`` se algum limite já foi atingido."""
        with self._lock, self._shared_file():
            now = self._clock()
            self._sync(now)
            self._forget_old_calls(now)
            if self._max_per_minute and len(self._recent) >= self._max_per_minute:
                raise ProviderError.limit_reached("minuto")
            if self._max_per_day and self._calls >= self._max_per_day:
                raise ProviderError.limit_reached("dia")
            self._recent.append(now)
            self._calls += 1
            self._save()

    def add_tokens(self, usage: Usage) -> None:
        with self._lock, self._shared_file():
            self._sync(self._clock())
            self._input_tokens += usage.input_tokens
            self._output_tokens += usage.output_tokens
            self._save()

    def snapshot(self) -> UsageSnapshot:
        with self._lock:
            now = self._clock()
            self._sync(now)
            self._forget_old_calls(now)
            return UsageSnapshot(
                calls_last_minute=len(self._recent),
                calls_today=self._calls,
                input_tokens_today=self._input_tokens,
                output_tokens_today=self._output_tokens,
                max_calls_per_minute=self._max_per_minute,
                max_calls_per_day=self._max_per_day,
            )

    @contextmanager
    def _shared_file(self) -> Iterator[None]:
        """Trava o total do dia entre processos, para ler, somar e gravar sem perder ninguém."""
        if self._path is None:
            yield
            return
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._path.with_name(f"{self._path.name}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _forget_old_calls(self, now: datetime) -> None:
        limit = now - timedelta(minutes=1)
        while self._recent and self._recent[0] <= limit:
            self._recent.popleft()

    def _sync(self, now: datetime) -> None:
        """Põe na memória o total de hoje. O arquivo manda: outro processo pode ter somado."""
        today = now.date()
        if self._path is None:
            if today != self._day:
                self._calls = self._input_tokens = self._output_tokens = 0
            self._day = today
            return
        data = read_toml(self._path)
        same_day = data.get("date") == today.isoformat()
        self._day = today
        self._calls = int(data.get("calls", 0)) if same_day else 0
        self._input_tokens = int(data.get("input_tokens", 0)) if same_day else 0
        self._output_tokens = int(data.get("output_tokens", 0)) if same_day else 0

    def _save(self) -> None:
        if self._path is None:
            return
        write_toml(
            self._path,
            {
                "date": self._day.isoformat(),
                "calls": self._calls,
                "input_tokens": self._input_tokens,
                "output_tokens": self._output_tokens,
            },
            mode=0o644,
        )
