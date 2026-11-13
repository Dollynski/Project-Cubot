"""Áudio: escolha do microfone e do alto-falante."""

from nicegui import run, ui

from cubo.errors import SetupError
from cubo.voice import load_devices
from cubo.web.forms import apply_config, updated, with_current
from cubo.web.layout import section
from cubo.web.panel import Panel
from cubo.web.widgets import problem_card

DEFAULT_DEVICE = "Padrão do sistema"
LEVEL_GAIN = 6.0


def build(panel: Panel) -> None:
    service = panel.service
    voice = service.config.voice
    try:
        devices = load_devices().list_devices()
    except SetupError as error:
        problem_card(str(error), "/audio", "Depois de instalar, recarregue esta página")
        devices = []

    inputs = {"": DEFAULT_DEVICE, **{d.name: d.name for d in devices if d.inputs}}
    outputs = {"": DEFAULT_DEVICE, **{d.name: d.name for d in devices if d.outputs}}

    async def play_test() -> None:
        session = service.voice
        if session is None:
            ui.notify("A voz está desligada: não há alto-falante para testar.", type="warning")
            return
        await run.io_bound(session.say, "Teste de som. Eu sou o Cubô.")

    async def save() -> None:
        new = updated(
            service.config,
            voice={"input_device": input_select.value, "output_device": output_select.value},
        )
        await apply_config(service, new)

    with section("Microfone", "Escolha qual microfone o Cubô escuta."):
        input_select = ui.select(
            with_current(inputs, voice.input_device), value=voice.input_device, label="Entrada"
        ).classes("w-full")
        level = ui.linear_progress(value=0, show_value=False).props("instant-feedback")
        ui.label("Fale perto do microfone: a barra deve se mexer.").classes("text-sm opacity-70")
    with section("Alto-falante", "O teste usa o alto-falante que já está salvo."):
        output_select = ui.select(
            with_current(outputs, voice.output_device), value=voice.output_device, label="Saída"
        ).classes("w-full")
        ui.button("Testar som", icon="volume_up", on_click=play_test).props("outline")
    ui.button("Salvar", icon="save", on_click=save)

    def tick() -> None:
        session = service.voice
        level.set_value(
            min(1.0, session.mic_level * LEVEL_GAIN) if session and session.running else 0
        )

    ui.timer(0.25, tick)
