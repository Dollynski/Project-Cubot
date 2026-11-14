"""Início: o que o Cubô está fazendo, a conversa recente e o uso da IA."""

from nicegui import run, ui

from cubo.web.layout import section
from cubo.web.panel import Panel
from cubo.web.widgets import (
    STATE_COLORS,
    latency_summary,
    problem_card,
    usage_summary,
    warning_card,
)

# O volume (RMS) da fala fica perto de 0,1; a barra amplia para ficar legível.
LEVEL_GAIN = 6.0
PROBLEM_FIXES = {"ia": ("/ia", "Configurar a IA"), "voz": ("/voz", "Ver as configurações de voz")}


def build(panel: Panel) -> None:
    service = panel.service

    @ui.refreshable
    def status() -> None:
        for name, message in service.problems.items():
            path, label = PROBLEM_FIXES[name]
            problem_card(message, path, label)
        for warning in service.warnings:
            warning_card(warning)
        voice = service.voice
        if voice is not None and voice.error:
            problem_card(f"O ciclo de voz parou: {voice.error}", "/", "Use o botão para religar")
        with section("Estado"):
            if not service.voice_enabled:
                ui.label("Modo sem voz: o microfone não foi ligado (comando `cubo painel`).")
            elif voice is None or not voice.running:
                ui.label("A voz está desligada.").classes("font-medium")
                ui.button("Ligar a voz", on_click=restart_voice)
            else:
                state = service.activity.state
                ui.badge(state.value, color=STATE_COLORS[state.value]).classes("text-base p-2")

    async def restart_voice() -> None:
        await run.io_bound(service.restart_voice)
        status.refresh()

    @ui.refreshable
    def conversation() -> None:
        entries = service.activity.entries()
        if not entries:
            ui.label("Nada foi dito ainda. Chame o Cubô pela palavra de ativação.").classes(
                "opacity-70"
            )
        for entry in entries[-20:]:
            ui.chat_message(
                entry.text,
                name="Você" if entry.author == "you" else "Cubô",
                stamp=entry.time.strftime("%H:%M"),
                sent=entry.author == "you",
            ).classes("w-full")

    @ui.refreshable
    def usage() -> None:
        usage_summary(service)

    @ui.refreshable
    def latency() -> None:
        latency_summary(service.activity.timings())

    status()
    with section("Microfone"):
        level = ui.linear_progress(value=0, show_value=False).props("instant-feedback")
    with section("Conversa recente"):
        conversation()
    with section("Tempo de resposta"):
        latency()
    with section("Uso da IA"):
        usage()

    shown = {
        "entries": len(service.activity.entries()),
        "timings": len(service.activity.timings()),
        "state": service.activity.state,
    }

    def tick() -> None:
        voice = service.voice
        level.set_value(min(1.0, voice.mic_level * LEVEL_GAIN) if voice and voice.running else 0)
        entries = service.activity.entries()
        if len(entries) != shown["entries"]:
            shown["entries"] = len(entries)
            conversation.refresh()
            usage.refresh()
        if len(service.activity.timings()) != shown["timings"]:
            shown["timings"] = len(service.activity.timings())
            latency.refresh()
        if service.activity.state != shown["state"]:
            shown["state"] = service.activity.state
            status.refresh()

    ui.timer(0.25, tick)
    ui.timer(10.0, usage.refresh)
