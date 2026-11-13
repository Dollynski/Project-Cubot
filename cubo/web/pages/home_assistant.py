"""Casa: conexão com o Home Assistant e os dispositivos que o Cubô pode usar."""

from nicegui import run, ui
from pydantic import ValidationError

from cubo.config import Device
from cubo.tools.home_assistant import HomeAssistantError, verify_connection
from cubo.web.forms import apply_config, first_error, secret_field, updated
from cubo.web.layout import section
from cubo.web.panel import Panel

CREDENTIAL = "home_assistant"


def build(panel: Panel) -> None:
    service = panel.service
    home = service.config.home_assistant
    devices: list[dict[str, str]] = [device.model_dump() for device in home.devices]

    async def check(token: str | None = None) -> str | None:
        """Testa a conexão com o token digitado (ou o salvo). Retorna o token usado, ou ``None``."""
        value = token or service.credentials.get(CREDENTIAL)
        if not value:
            ui.notify("Informe o token de acesso.", type="warning")
            return None
        try:
            await run.io_bound(verify_connection, url.value.strip(), value)
        except HomeAssistantError as error:
            ui.notify(str(error), type="negative", multi_line=True)
            return None
        return value

    async def test_connection() -> None:
        if await check(token.value.strip()):
            ui.notify("Conexão com o Home Assistant funcionando.", type="positive")

    async def save_token() -> None:
        typed = token.value.strip()
        if not typed:
            ui.notify("Digite o token para salvar.", type="warning")
            return
        if await check(typed):
            await run.io_bound(service.save_credential, CREDENTIAL, typed)
            ui.notify("Token válido e salvo.", type="positive")
            token.set_value("")

    async def remove_token() -> None:
        await run.io_bound(service.delete_credential, CREDENTIAL)
        ui.notify("Token removido.")

    def add_device() -> None:
        try:
            device = Device(entity_id=entity.value.strip(), alias=alias.value.strip())
        except ValidationError as error:
            ui.notify(first_error(error), type="negative")
            return
        devices.append(device.model_dump())
        alias.set_value("")
        entity.set_value("")
        device_list.refresh()

    def remove_device(index: int) -> None:
        del devices[index]
        device_list.refresh()

    async def save() -> None:
        try:
            new = updated(
                service.config, home_assistant={"url": url.value.strip(), "devices": devices}
            )
        except ValidationError as error:
            ui.notify(first_error(error), type="negative")
            return
        await apply_config(service, new)

    with section(
        "Conexão", "No Home Assistant: seu perfil, Segurança, token de acesso de longa duração."
    ):
        url = ui.input("Endereço do Home Assistant", value=home.url).classes("w-full")
        token = secret_field("Token de acesso", service.credentials.masked(CREDENTIAL))
        with ui.row():
            ui.button("Testar conexão", icon="wifi_tethering", on_click=test_connection).props(
                "outline"
            )
            ui.button("Validar e salvar o token", icon="key", on_click=save_token)
            ui.button("Remover o token", on_click=remove_token).props("flat color=negative")
    with section(
        "Dispositivos", "Cada um com o nome pelo qual você vai chamá-lo (ex.: luz da sala)."
    ):

        @ui.refreshable
        def device_list() -> None:
            if not devices:
                ui.label("Nenhum dispositivo cadastrado.").classes("opacity-70")
            for index, device in enumerate(devices):
                with ui.row().classes("items-center w-full no-wrap"):
                    ui.label(device["alias"]).classes("font-medium")
                    ui.label(device["entity_id"]).classes("text-sm opacity-70 grow")
                    ui.button(icon="delete", on_click=lambda i=index: remove_device(i)).props(
                        "flat round dense color=negative"
                    )

        device_list()
        ui.separator()
        alias = ui.input("Nome falado", placeholder="luz da sala").classes("w-full")
        entity = ui.input(
            "ID da entidade",
            placeholder="light.sala",
        ).props('hint="Aparece no Home Assistant em Ferramentas de desenvolvedor, Estados."')
        entity.classes("w-full")
        ui.button("Adicionar", icon="add", on_click=add_device).props("outline")
    ui.button("Salvar", icon="save", on_click=save)
