"""Logs que nunca mostram chaves de API ou tokens."""

import logging
import re
from collections.abc import Callable, Iterable
from typing import TextIO

MASK = "[chave oculta]"

# Formatos comuns de chave, para mascarar mesmo o que não foi cadastrado no Cubô.
_KEY_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),  # OpenAI e Anthropic
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),  # Google
    re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"),  # JWT, como o token do Home Assistant
)

# Valores curtos demais mascarariam pedaços de texto comum.
_MIN_SECRET_LENGTH = 8

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def redact(text: str, secrets: Iterable[str]) -> str:
    """Troca cada segredo conhecido e cada texto com formato de chave por ``MASK``."""
    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, MASK)
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(MASK, text)
    return text


class RedactingFormatter(logging.Formatter):
    """Mascara segredos na linha já formatada, incluindo tracebacks de exceções."""

    def __init__(self, fmt: str, secrets: Callable[[], Iterable[str]]) -> None:
        super().__init__(fmt)
        self._secrets = secrets

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets())


def configure_logging(
    secrets: Callable[[], Iterable[str]],
    *,
    level: int = logging.INFO,
    stream: TextIO | None = None,
) -> None:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter(_LOG_FORMAT, secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Cada requisição HTTP dos SDKs vira uma linha em INFO; só interessa quando dá problema.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
