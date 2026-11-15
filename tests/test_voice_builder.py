import builtins
import hashlib
from pathlib import Path

import pytest

from cubo.config import VoiceSettings
from cubo.errors import SetupError
from cubo.voice import builder, load_devices, models
from cubo.voice.builder import (
    load_synthesizer,
    load_transcriber,
    load_wake_word,
    parse_device,
)
from cubo.voice.models import piper_voice_path, wake_word_path


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", None),
        ("  ", None),
        ("3", 3),
        (" 12 ", 12),
        ("USB Audio", "USB Audio"),
        ("hw:1,0", "hw:1,0"),
    ],
)
def test_parse_device(value, expected):
    assert parse_device(value) == expected


def test_missing_ready_wake_word_points_to_prepare(tmp_path):
    with pytest.raises(SetupError, match="cubo preparar"):
        load_wake_word(VoiceSettings(), tmp_path)


def test_missing_custom_wake_word_names_the_file(tmp_path):
    settings = VoiceSettings(wake_word=str(tmp_path / "meu.onnx"))

    with pytest.raises(SetupError, match="meu.onnx") as error:
        load_wake_word(settings, tmp_path)

    assert "preparar" not in str(error.value)


def install_ready_made_wake_word(tmp_path, monkeypatch, settings, content=b"onnx"):
    """Põe um modelo pronto na pasta, com o SHA-256 fixado igual ao do conteúdo de teste."""
    monkeypatch.setitem(
        models.WAKE_WORD_SHA256, settings.wake_word, hashlib.sha256(b"onnx").hexdigest()
    )
    path = wake_word_path(settings.wake_word, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_wake_word_gets_the_model_and_threshold(tmp_path, monkeypatch):
    created = []
    monkeypatch.setattr(builder, "WakeWordDetector", lambda *args: created.append(args) or "ok")
    settings = VoiceSettings(wake_word_threshold=0.7)
    path = install_ready_made_wake_word(tmp_path, monkeypatch, settings)

    assert load_wake_word(settings, tmp_path) == "ok"
    assert created == [(path, 0.7)]


def test_missing_transcription_model_points_to_prepare(tmp_path):
    with pytest.raises(SetupError, match="cubo preparar"):
        load_transcriber(VoiceSettings(), tmp_path)


def add_piper_voice(settings: VoiceSettings, data_dir: Path) -> Path:
    path = piper_voice_path(settings.piper_voice, data_dir)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"onnx")
    path.with_name(f"{path.name}.json").write_text("{}")
    return path


def test_prefers_the_piper_voice(tmp_path, monkeypatch):
    created = []
    monkeypatch.setattr(
        builder, "PiperSynthesizer", lambda path, speed: created.append((path, speed)) or "piper"
    )
    settings = VoiceSettings(speech_speed=1.2)
    path = add_piper_voice(settings, tmp_path)
    warnings = []

    assert load_synthesizer(settings, tmp_path, warnings) == "piper"
    assert created == [(path, 1.2)]
    assert warnings == []


def test_falls_back_to_espeak_with_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/espeak-ng")
    warnings = []

    synthesizer = load_synthesizer(VoiceSettings(), tmp_path, warnings)

    assert isinstance(synthesizer, builder.EspeakSynthesizer)
    assert "espeak-ng" in warnings[0]
    assert "cubo preparar" in warnings[0]


def test_voice_without_the_json_config_is_not_used(tmp_path, monkeypatch):
    settings = VoiceSettings()
    add_piper_voice(settings, tmp_path).with_name(f"{settings.piper_voice}.onnx.json").unlink()
    monkeypatch.setattr(builder.shutil, "which", lambda _name: None)

    with pytest.raises(SetupError, match="cubo preparar"):
        load_synthesizer(settings, tmp_path, [])


def test_no_voice_at_all_is_a_setup_error(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.shutil, "which", lambda _name: None)

    with pytest.raises(SetupError, match="cubo preparar"):
        load_synthesizer(VoiceSettings(), tmp_path, [])


def test_missing_portaudio_explains_how_to_install(monkeypatch):
    real_import = builtins.__import__

    def without_portaudio(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cubo.voice" and "devices" in (fromlist or ()):
            raise OSError("PortAudio library not found")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", without_portaudio)

    with pytest.raises(SetupError, match="libportaudio2"):
        load_devices()


# ---- modelos corrompidos ou que não carregam: viram aviso, nunca traceback


def test_a_truncated_ready_made_wake_word_is_refused_with_the_repair_hint(tmp_path, monkeypatch):
    settings = VoiceSettings()
    install_ready_made_wake_word(tmp_path, monkeypatch, settings, content=b"onn")

    with pytest.raises(SetupError, match="corrompido ou incompleto") as error:
        load_wake_word(settings, tmp_path)

    assert "cubo preparar" in str(error.value)


def test_a_wake_word_that_is_a_folder_is_refused(tmp_path):
    settings = VoiceSettings()
    wake_word_path(settings.wake_word, tmp_path).mkdir(parents=True)

    with pytest.raises(SetupError, match="corrompido ou incompleto"):
        load_wake_word(settings, tmp_path)


def test_a_custom_wake_word_that_is_not_a_model_becomes_a_setup_error(tmp_path):
    garbage = tmp_path / "meu.onnx"
    garbage.write_bytes(b"isto nao e um modelo")

    # Sem trocar nada por fakes: é a biblioteca de verdade que recusa o arquivo.
    with pytest.raises(SetupError, match="Não consegui carregar o modelo de wake word") as error:
        load_wake_word(VoiceSettings(wake_word=str(garbage)), tmp_path)

    assert "modelo de wake word válido" in str(error.value)
    assert error.value.__cause__ is not None


def test_a_transcription_model_that_fails_to_load_becomes_a_setup_error(tmp_path, monkeypatch):
    def broken(*_args):
        raise RuntimeError("model.bin truncado")

    monkeypatch.setattr(builder, "Transcriber", broken)

    with pytest.raises(SetupError, match="model.bin truncado") as error:
        load_transcriber(VoiceSettings(), tmp_path)

    assert "cubo preparar" in str(error.value)


def test_a_corrupt_piper_voice_falls_back_to_espeak_with_a_warning(tmp_path, monkeypatch):
    settings = VoiceSettings()
    add_piper_voice(settings, tmp_path)

    def broken(*_args, **_options):
        raise ValueError("onnx inválido")

    monkeypatch.setattr(builder, "PiperSynthesizer", broken)
    monkeypatch.setattr(builder.shutil, "which", lambda _name: "/usr/bin/espeak-ng")
    warnings = []

    synthesizer = load_synthesizer(settings, tmp_path, warnings)

    assert isinstance(synthesizer, builder.EspeakSynthesizer)
    assert "onnx inválido" in warnings[0]
    assert "espeak-ng" in warnings[0]


def test_a_corrupt_piper_voice_without_espeak_is_a_setup_error(tmp_path, monkeypatch):
    settings = VoiceSettings()
    voice = add_piper_voice(settings, tmp_path)

    def broken(*_args, **_options):
        raise ValueError("onnx inválido")

    monkeypatch.setattr(builder, "PiperSynthesizer", broken)
    monkeypatch.setattr(builder.shutil, "which", lambda _name: None)

    with pytest.raises(SetupError, match="onnx inválido") as error:
        load_synthesizer(settings, tmp_path, [])

    # Só rodar `cubo preparar` não conserta: ele pula o que já existe, então manda apagar.
    assert str(voice) in str(error.value)
    assert "Apague" in str(error.value)
