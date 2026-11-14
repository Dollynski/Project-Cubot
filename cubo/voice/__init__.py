"""Pipeline de voz: wake word, escuta, transcrição, fala."""

from types import ModuleType

from cubo.errors import SetupError


def load_devices() -> ModuleType:
    """Importa o módulo de áudio, que exige a biblioteca PortAudio instalada no sistema."""
    try:
        from cubo.voice import devices
    except OSError as error:
        raise SetupError(
            "Falta a biblioteca PortAudio. Instale com `sudo apt install libportaudio2`."
        ) from error
    return devices
