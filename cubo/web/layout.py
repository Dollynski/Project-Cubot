"""Estrutura comum das páginas: cabeçalho com a navegação e uma coluna de conteúdo."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from nicegui import ui

NAVIGATION = (
    ("/", "Início"),
    ("/audio", "Áudio"),
    ("/voz", "Voz e fala"),
    ("/ia", "IA"),
    ("/casa", "Casa"),
    ("/seguranca", "Segurança"),
)


@contextmanager
def frame(current: str, on_sign_out: Callable[[], None]) -> Iterator[None]:
    with ui.header(elevated=True).classes("items-center gap-2 no-wrap"):
        ui.label("Cubô").classes("text-xl font-bold mr-2")
        with ui.row().classes("gap-1 no-wrap overflow-x-auto grow"):
            for path, label in NAVIGATION:
                button = ui.button(label, on_click=lambda target=path: ui.navigate.to(target))
                button.props("dense unelevated" if path == current else "dense flat")
                button.classes("text-white")
        ui.button(icon="logout", on_click=on_sign_out).props("flat round dense").tooltip("Sair")
    with ui.column().classes("w-full max-w-3xl mx-auto gap-4 p-2"):
        yield


@contextmanager
def section(title: str, hint: str = "") -> Iterator[None]:
    with ui.card().classes("w-full gap-2"):
        ui.label(title).classes("text-lg font-medium")
        if hint:
            ui.label(hint).classes("text-sm opacity-70")
        yield


@contextmanager
def centered(title: str) -> Iterator[None]:
    """Cartão no meio da tela, para o login e o primeiro acesso."""
    column = ui.column().classes("w-full items-center justify-center min-h-screen p-4")
    with column, ui.card().classes("w-full max-w-sm gap-3"):
        ui.label(title).classes("text-xl font-bold")
        yield
