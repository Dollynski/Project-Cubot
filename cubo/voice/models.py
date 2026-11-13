"""Onde ficam os modelos de voz e como baixá-los (`cubo preparar`)."""

import hashlib
import os
import tempfile
from pathlib import Path

import httpx2

# Modelos prontos de wake word, fixados numa versão e conferidos pelo SHA-256 publicado no GitHub.
WAKE_WORD_URL = "https://github.com/livekit/livekit-wakeword/releases/download/v2.1.2/{name}.onnx"
WAKE_WORD_SHA256 = {
    "hey_jarvis": "8b554c50809888ac14f67fa21acc3bd85e58f5678ee4f2be5d0041f9a2e62843",
    "hey_livekit": "6ca579367f62792a5e6d981a10751e6deedd7b2f7a00b08342b7fcd9bb867231",
}

DOWNLOAD_TIMEOUT_SECONDS = 120.0


class DownloadError(Exception):
    """O download falhou ou o arquivo não é o esperado."""


def default_data_dir() -> Path:
    """Pasta dos modelos: ``$CUBO_DATA_DIR`` ou ``$XDG_DATA_HOME/cubo``."""
    if override := os.environ.get("CUBO_DATA_DIR"):
        return Path(override)
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "cubo"


def wake_word_path(wake_word: str, data_dir: Path) -> Path:
    """Caminho do modelo: um dos prontos (na pasta de dados) ou o ``.onnx`` do próprio usuário."""
    if wake_word in WAKE_WORD_SHA256:
        return data_dir / "wakeword" / f"{wake_word}.onnx"
    return Path(wake_word).expanduser()


def piper_voice_path(voice: str, data_dir: Path) -> Path:
    return data_dir / "piper" / f"{voice}.onnx"


def whisper_dir(data_dir: Path) -> Path:
    return data_dir / "whisper"


def download_wake_word(name: str, data_dir: Path, http: httpx2.Client) -> Path:
    """Baixa um modelo pronto de wake word, se ainda não estiver na pasta e íntegro."""
    if name not in WAKE_WORD_SHA256:
        raise DownloadError(f"{name} não é um modelo pronto; informe o caminho de um .onnx.")
    target = wake_word_path(name, data_dir)
    expected = WAKE_WORD_SHA256[name]
    if target.exists() and _sha256(target.read_bytes()) == expected:
        return target
    try:
        response = http.get(WAKE_WORD_URL.format(name=name), follow_redirects=True)
        response.raise_for_status()
    except httpx2.HTTPError as error:
        raise DownloadError(f"Não consegui baixar o modelo {name}: {error}") from error
    if _sha256(response.content) != expected:
        raise DownloadError(f"O modelo {name} baixado não confere com o SHA-256 esperado.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(response.content)
    temporary.replace(target)
    return target


def download_piper_voice(voice: str, data_dir: Path) -> Path:
    """Baixa a voz do Piper. O download é numa pasta temporária, então nunca sobra meio arquivo."""
    # Importado aqui: só o comando de preparo precisa do downloader do Piper.
    from piper.download_voices import download_voice

    target = piper_voice_path(voice, data_dir)
    if target.exists() and target.with_name(f"{target.name}.json").exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        try:
            download_voice(voice, Path(staging))
        except (OSError, ValueError) as error:
            raise DownloadError(f"Não consegui baixar a voz {voice}: {error}") from error
        # O .onnx vai por último: se ele existe, a voz está completa.
        for suffix in (".onnx.json", ".onnx"):
            (Path(staging) / f"{voice}{suffix}").replace(target.parent / f"{voice}{suffix}")
    return target


def download_whisper(model: str, data_dir: Path) -> None:
    from faster_whisper import download_model

    try:
        download_model(model, cache_dir=str(whisper_dir(data_dir)))
    except (OSError, ValueError) as error:
        raise DownloadError(f"Não consegui baixar o modelo {model} do Whisper: {error}") from error


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
