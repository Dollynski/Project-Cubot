"""Sessão de quem está usando o painel (login válido por algumas horas)."""

import time

from nicegui import app, ui

SESSION_SECONDS = 12 * 60 * 60
SIGNED_IN_AT = "signed_in_at"


def sign_in() -> None:
    app.storage.user[SIGNED_IN_AT] = time.time()


def sign_out() -> None:
    app.storage.user.clear()


def is_signed_in() -> bool:
    signed_in_at = app.storage.user.get(SIGNED_IN_AT)
    return signed_in_at is not None and time.time() - signed_in_at < SESSION_SECONDS


def client_address() -> str:
    """Endereço de quem fez o pedido, para o bloqueio por tentativas."""
    client = ui.context.client.request.client
    return client.host if client else "desconhecido"
