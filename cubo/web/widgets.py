"""Peças de interface usadas em mais de uma página."""

from nicegui import ui

from cubo.service import CuboService

NO_LIMIT = "sem limite"
STATE_COLORS = {
    "aguardando": "grey",
    "ouvindo": "green",
    "transcrevendo": "blue",
    "pensando": "purple",
    "falando": "orange",
}


def usage_summary(service: CuboService) -> None:
    usage = service.usage.snapshot()

    def limit(value: int) -> str:
        return str(value) if value else NO_LIMIT

    ui.label(
        f"Chamadas à IA: {usage.calls_last_minute} no último minuto (limite: "
        f"{limit(usage.max_calls_per_minute)}) e {usage.calls_today} hoje "
        f"(limite: {limit(usage.max_calls_per_day)})."
    )
    ui.label(
        f"Tokens hoje: {usage.input_tokens_today:,} de entrada e "
        f"{usage.output_tokens_today:,} de saída.".replace(",", ".")
    )


def problem_card(message: str, fix_path: str, fix_label: str) -> None:
    with ui.card().classes("w-full bg-red-100 text-red-900 gap-1"):
        ui.label(message)
        ui.link(fix_label, fix_path).classes("text-red-900 underline")


def warning_card(message: str) -> None:
    with ui.card().classes("w-full bg-amber-100 text-amber-900"):
        ui.label(message)
