"""Peças de interface usadas em mais de uma página."""

from collections.abc import Sequence

from nicegui import ui

from cubo.service import CuboService
from cubo.voice.timing import Timing

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


def format_seconds(value: float | None) -> str:
    """Segundos com uma casa e vírgula (1,8 s), ou um traço quando a etapa não aconteceu."""
    return "—" if value is None else f"{value:.1f}".replace(".", ",") + " s"


def average_timing(timings: Sequence[Timing]) -> Timing | None:
    """Média de cada etapa, ignorando os pedidos em que ela não aconteceu."""
    if not timings:
        return None

    def mean(field: str) -> float | None:
        values = [value for timing in timings if (value := getattr(timing, field)) is not None]
        return sum(values) / len(values) if values else None

    return Timing(
        transcription=mean("transcription") or 0.0,
        first_text=mean("first_text"),
        reply=mean("reply") or 0.0,
        first_sound=mean("first_sound"),
        total=mean("total") or 0.0,
    )


TIMING_ROWS = (
    ("Transcrição da fala", "transcription"),
    ("A IA começa a responder", "first_text"),
    ("A IA termina de responder", "reply"),
    ("O Cubô começa a falar", "first_sound"),
    ("O Cubô termina de falar", "total"),
)


def latency_summary(timings: Sequence[Timing]) -> None:
    last, average = (timings[-1], average_timing(timings)) if timings else (None, None)
    if last is None or average is None:
        ui.label("Ainda não há pedidos medidos.").classes("opacity-70")
        return
    rows = [
        {
            "stage": label,
            "last": format_seconds(getattr(last, field)),
            "average": format_seconds(getattr(average, field)),
        }
        for label, field in TIMING_ROWS
    ]
    columns = [
        {"name": "stage", "label": "Etapa", "field": "stage", "align": "left"},
        {"name": "last", "label": "Último pedido", "field": "last", "align": "right"},
        {
            "name": "average",
            "label": f"Média dos últimos {len(timings)}",
            "field": "average",
            "align": "right",
        },
    ]
    ui.table(columns=columns, rows=rows, row_key="stage").classes("w-full").props("dense flat")
    ui.label(
        "Os tempos contam a partir do fim da gravação do pedido. "
        'O "começa a falar" é o que você sente de espera.'
    ).classes("text-sm opacity-70")
