"""Comparação de modelos de voz: quanto tempo cada um leva e quanto erra, para escolher o melhor."""

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from cubo.voice.audio import SAMPLE_RATE, AudioClip, resample

# Pedidos parecidos com os que o Cubô recebe em casa.
PHRASES = (
    "Acende a luz da sala, por favor.",
    "Qual é a temperatura do quarto agora?",
    "Desliga o ventilador e apaga a luz do corredor.",
    "Me conta uma piada curta sobre computadores.",
    "Que horas são e como vai estar o tempo amanhã?",
)


def words(text: str) -> list[str]:
    """Palavras em minúsculas e sem pontuação, para comparar o que foi dito com o que foi ouvido."""
    return re.findall(r"[\w']+", text.lower())


def word_error_rate(reference: str, heard: str) -> float:
    """Proporção de palavras trocadas, faltando ou sobrando (0 é perfeito)."""
    expected, actual = words(reference), words(heard)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, word in enumerate(expected, start=1):
        current = [row]
        for column, other in enumerate(actual, start=1):
            cost = 0 if word == other else 1
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost)
            )
        previous = current
    return previous[-1] / len(expected)


@dataclass(frozen=True)
class Transcription:
    phrase: str
    heard: str
    audio_seconds: float
    seconds: float

    @property
    def error(self) -> float:
        return word_error_rate(self.phrase, self.heard)


@dataclass
class ModelResult:
    model: str
    load_seconds: float
    transcriptions: list[Transcription] = field(default_factory=list)

    @property
    def mean_seconds(self) -> float:
        return sum(item.seconds for item in self.transcriptions) / len(self.transcriptions)

    @property
    def real_time_factor(self) -> float:
        """Tempo gasto por segundo de áudio: abaixo de 1 é mais rápido que a fala."""
        return sum(item.seconds for item in self.transcriptions) / sum(
            item.audio_seconds for item in self.transcriptions
        )

    @property
    def mean_error(self) -> float:
        return sum(item.error for item in self.transcriptions) / len(self.transcriptions)


@dataclass(frozen=True)
class Synthesis:
    phrase: str
    audio_seconds: float
    seconds: float


def synthesize_phrases(
    synthesizer, phrases: Sequence[str] = PHRASES, clock: Callable[[], float] = time.perf_counter
) -> tuple[list[tuple[str, np.ndarray]], list[Synthesis]]:
    """Gera a fala de cada frase (a 16 kHz, pronta para transcrever) e mede a síntese."""
    clips, timings = [], []
    for phrase in phrases:
        started = clock()
        clip: AudioClip = synthesizer.synthesize(phrase)
        seconds = clock() - started
        audio = resample(clip, SAMPLE_RATE).samples
        clips.append((phrase, audio))
        timings.append(Synthesis(phrase, len(audio) / SAMPLE_RATE, seconds))
    return clips, timings


def benchmark_models(
    models: Sequence[str],
    make_transcriber: Callable[[str], object],
    clips: Sequence[tuple[str, np.ndarray]],
    *,
    repetitions: int = 1,
    clock: Callable[[], float] = time.perf_counter,
) -> list[ModelResult]:
    """Carrega cada modelo e transcreve as frases, medindo o tempo (depois de aquecer)."""
    results = []
    for model in models:
        started = clock()
        transcriber = make_transcriber(model)
        result = ModelResult(model, load_seconds=clock() - started)
        transcriber.warm_up()
        for phrase, audio in clips:
            for _ in range(repetitions):
                started = clock()
                heard = transcriber.transcribe(audio)
                result.transcriptions.append(
                    Transcription(phrase, heard, len(audio) / SAMPLE_RATE, clock() - started)
                )
        results.append(result)
    return results


def format_report(results: Sequence[ModelResult], synthesis: Sequence[Synthesis]) -> str:
    lines = ["Transcrição (Whisper)", ""]
    header = f"{'modelo':<12}{'carga':>9}{'por frase':>12}{'fator':>9}{'erro de palavras':>20}"
    lines += [header, "-" * len(header)]
    for result in results:
        lines.append(
            f"{result.model:<12}{result.load_seconds:>8.1f}s{result.mean_seconds:>11.2f}s"
            f"{result.real_time_factor:>9.2f}{result.mean_error:>19.0%}"
        )
    lines += [
        "",
        "fator = tempo gasto por segundo de áudio (abaixo de 1 é mais rápido que a fala).",
        "",
        "Síntese (Piper)",
        "",
    ]
    if synthesis:
        total_audio = sum(item.audio_seconds for item in synthesis)
        total = sum(item.seconds for item in synthesis)
        lines.append(
            f"{len(synthesis)} frases, {total / len(synthesis):.2f}s por frase, "
            f"fator {total / total_audio:.2f}"
        )
    return "\n".join(lines)
