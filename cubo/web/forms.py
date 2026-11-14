"""Ajudas dos formulários: montar a configuração nova, aplicá-la e avisar o resultado."""

import logging
from typing import Any

from nicegui import run, ui
from pydantic import ValidationError

from cubo.config import Config
from cubo.errors import SetupError
from cubo.service import CuboService

logger = logging.getLogger(__name__)


def updated(config: Config, **sections: dict[str, Any]) -> Config:
    """Cópia da configuração com campos trocados, já validada.

    Levanta ``ValidationError`` se algum valor não servir (o chamador mostra a mensagem).
    """
    data = config.model_dump()
    for section, fields in sections.items():
        data[section].update(fields)
    return Config.model_validate(data)


def first_error(error: ValidationError) -> str:
    detail = error.errors()[0]
    where = ".".join(str(part) for part in detail["loc"])
    return f"{where}: {detail['msg']}"


async def apply_config(service: CuboService, new: Config) -> bool:
    """Aplica a configuração no serviço e avisa na tela. Retorna se deu certo."""
    notice = ui.notification("Aplicando...", spinner=True, timeout=None)
    try:
        # Carregar modelos leva tempo: roda fora do laço de eventos para o painel não travar.
        reloaded = await run.io_bound(service.apply, new)
    except SetupError as error:
        notice.dismiss()
        ui.notify(str(error), type="negative", multi_line=True)
        return False
    except Exception as error:
        logger.exception("Falha ao aplicar a configuração")
        notice.dismiss()
        ui.notify(f"Não consegui aplicar: {error}", type="negative", multi_line=True)
        return False
    notice.dismiss()
    detail = f" Recarregado: {', '.join(reloaded)}." if reloaded else ""
    ui.notify(f"Salvo.{detail}", type="positive")
    return True


def secret_field(label: str, masked: str | None) -> ui.input:
    """Campo só de escrita: nunca mostra o valor salvo, só o final dele, e vazio mantém a chave."""
    field = ui.input(label, password=True, placeholder=masked or "nada salvo")
    field.props("autocomplete=new-password").classes("w-full")
    if masked:
        field.props(f'hint="Salva: {masked}. Deixe vazio para manter."')
    return field


def with_current(options: dict[str, str], current: str) -> dict[str, str]:
    """Garante que o valor já configurado apareça na lista, mesmo que não exista mais."""
    if current in options:
        return options
    return {**options, current: f"{current} (configurado)"}


async def confirm(message: str, accept: str) -> bool:
    with ui.dialog() as dialog, ui.card():
        ui.label(message)
        with ui.row().classes("justify-end w-full"):
            ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(accept, on_click=lambda: dialog.submit(True))
    return bool(await dialog)
