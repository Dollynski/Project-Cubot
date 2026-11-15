"""Carrega os modelos de voz, um a um, a partir da configuração."""

import shutil
from pathlib import Path

from huggingface_hub.errors import LocalEntryNotFoundError

from cubo.config import VoiceSettings
from cubo.errors import SetupError
from cubo.voice.models import (
    WAKE_WORD_SHA256,
    piper_voice_path,
    wake_word_intact,
    wake_word_path,
    whisper_dir,
)
from cubo.voice.stt import Transcriber
from cubo.voice.tts import EspeakSynthesizer, PiperSynthesizer, Synthesizer
from cubo.voice.wake_word import WakeWordDetector


def parse_device(value: str) -> int | str | None:
    """Vazio é o dispositivo padrão; só dígitos é o número; o resto é parte do nome."""
    value = value.strip()
    if not value:
        return None
    return int(value) if value.isdigit() else value


def _load_failure(what: str, error: Exception, fix: str) -> SetupError:
    """Cada biblioteca de modelo levanta um tipo de erro; para o usuário, todos são um aviso."""
    return SetupError(f"Não consegui carregar {what}: {error}. {fix}")


def load_wake_word(settings: VoiceSettings, data_dir: Path) -> WakeWordDetector:
    path = wake_word_path(settings.wake_word, data_dir)
    ready_made = settings.wake_word in WAKE_WORD_SHA256
    if not path.exists():
        hint = " Rode `cubo preparar`." if ready_made else ""
        raise SetupError(f"Modelo de wake word não encontrado em {path}.{hint}")
    if ready_made and not wake_word_intact(settings.wake_word, data_dir):
        raise SetupError(
            f"O modelo de wake word em {path} está corrompido ou incompleto. "
            "Rode `cubo preparar` para baixar de novo."
        )
    try:
        return WakeWordDetector(path, settings.wake_word_threshold)
    except Exception as error:
        fix = (
            "Rode `cubo preparar` para baixar de novo."
            if ready_made
            else "Confira se o arquivo é um modelo de wake word válido."
        )
        raise _load_failure("o modelo de wake word", error, fix) from error


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
    except Exception as error:
        raise _load_failure(
            f"o modelo de transcrição '{settings.whisper_model}'",
            error,
            f"Apague a pasta {whisper_dir(data_dir)} e rode `cubo preparar` para baixar de novo.",
        ) from error


def load_synthesizer(settings: VoiceSettings, data_dir: Path, warnings: list[str]) -> Synthesizer:
    """Prefere a voz do Piper; sem ela (ou se ela não carregar), usa o espeak-ng se houver."""
    voice_path = piper_voice_path(settings.piper_voice, data_dir)
    voice_config = voice_path.with_name(f"{voice_path.name}.json")
    if voice_path.exists() and voice_config.exists():
        try:
            return PiperSynthesizer(voice_path, speed=settings.speech_speed)
        except Exception as error:
            failure = _load_failure(
                f"a voz {settings.piper_voice}",
                error,
                f"Apague {voice_path} e {voice_config} e rode `cubo preparar` para baixar de novo.",
            )
            if not shutil.which("espeak-ng"):
                raise failure from error
            warnings.append(f"{failure} Enquanto isso, usando o espeak-ng.")
            return EspeakSynthesizer(speed=settings.speech_speed)
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
