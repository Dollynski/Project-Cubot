"""Monta o ciclo de voz a partir da configuração."""

import shutil
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path

from huggingface_hub.errors import LocalEntryNotFoundError

from cubo.assistant import Assistant
from cubo.config import VoiceSettings
from cubo.errors import SetupError
from cubo.voice import load_devices
from cubo.voice.events import Event
from cubo.voice.listening import ListeningLimits, SpeechDetector, UtteranceRecorder
from cubo.voice.loop import Microphone, VoiceLoop
from cubo.voice.models import WAKE_WORD_SHA256, piper_voice_path, wake_word_path, whisper_dir
from cubo.voice.stt import Transcriber
from cubo.voice.tts import EspeakSynthesizer, PiperSynthesizer, Speaker, Synthesizer
from cubo.voice.wake_word import WakeWordDetector


@dataclass
class VoiceRuntime:
    loop: VoiceLoop
    microphone: AbstractContextManager[Microphone]  # precisa ser aberto com `with`
    warnings: list[str] = field(default_factory=list)


def parse_device(value: str) -> int | str | None:
    """Vazio é o dispositivo padrão; só dígitos é o número; o resto é parte do nome."""
    value = value.strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


def build_voice(
    settings: VoiceSettings,
    assistant: Assistant,
    data_dir: Path,
    on_event: Callable[[Event], None] = lambda _event: None,
) -> VoiceRuntime:
    """Cria o ciclo de voz. Levanta ``SetupError`` se faltar modelo ou dispositivo de áudio."""
    wake_word = load_wake_word(settings, data_dir)
    transcriber = load_transcriber(settings, data_dir)
    warnings: list[str] = []
    synthesizer = load_synthesizer(settings, data_dir, warnings)

    devices = load_devices()
    microphone = devices.Microphone(parse_device(settings.input_device))
    player = devices.SoundDevicePlayer(parse_device(settings.output_device))

    limits = ListeningLimits(
        silence_seconds=settings.silence_seconds, max_seconds=settings.max_listening_seconds
    )
    loop = VoiceLoop(
        microphone=microphone,
        wake_word=wake_word,
        recorder=UtteranceRecorder(SpeechDetector(), limits),
        transcriber=transcriber,
        assistant=assistant,
        speaker=Speaker(synthesizer, player),
        on_event=on_event,
    )
    return VoiceRuntime(loop=loop, microphone=microphone, warnings=warnings)


def load_wake_word(settings: VoiceSettings, data_dir: Path) -> WakeWordDetector:
    path = wake_word_path(settings.wake_word, data_dir)
    if not path.exists():
        hint = " Rode `cubo preparar`." if settings.wake_word in WAKE_WORD_SHA256 else ""
        raise SetupError(f"Modelo de wake word não encontrado em {path}.{hint}")
    return WakeWordDetector(path, settings.wake_word_threshold)


def load_transcriber(settings: VoiceSettings, data_dir: Path) -> Transcriber:
    try:
        return Transcriber(
            settings.whisper_model, settings.whisper_compute_type, whisper_dir(data_dir)
        )
    except LocalEntryNotFoundError as error:
        raise SetupError(
            f"O modelo de transcrição '{settings.whisper_model}' não foi baixado. "
            "Rode `cubo preparar`."
        ) from error


def load_synthesizer(settings: VoiceSettings, data_dir: Path, warnings: list[str]) -> Synthesizer:
    """Prefere a voz do Piper; sem ela, usa o espeak-ng se estiver instalado."""
    voice_path = piper_voice_path(settings.piper_voice, data_dir)
    voice_config = voice_path.with_name(f"{voice_path.name}.json")
    if voice_path.exists() and voice_config.exists():
        return PiperSynthesizer(voice_path, speed=settings.speech_speed)
    if shutil.which("espeak-ng"):
        warnings.append(
            f"A voz {settings.piper_voice} não foi baixada; usando o espeak-ng. "
            "Rode `cubo preparar` para uma voz mais natural."
        )
        return EspeakSynthesizer(speed=settings.speech_speed)
    raise SetupError(
        f"A voz {settings.piper_voice} não foi baixada e o espeak-ng não está instalado. "
        "Rode `cubo preparar`."
    )
