import os
import signal
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import cubo.__main__ as cli
from cubo.assistant import Assistant
from cubo.bootstrap import Runtime
from cubo.config import default_config_dir, load_config
from cubo.credentials import CredentialStore
from cubo.errors import SetupError
from cubo.llm.memory import ConversationMemory
from cubo.tools.registry import ToolRegistry
from cubo.voice import models
from cubo.voice.events import Heard, Replied
from cubo.voice.models import DownloadError
from tests.test_assistant import FakeProvider


def secrets_file() -> Path:
    return default_config_dir() / "secrets.toml"


def test_key_command_saves_a_private_secret(monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "AIza-colada-1234")

    assert cli.main(["chave", "gemini"]) == 0

    assert CredentialStore(secrets_file(), environ={}).get("gemini") == "AIza-colada-1234"
    assert stat.S_IMODE(secrets_file().stat().st_mode) == 0o600
    assert "••••1234" in capsys.readouterr().out


def test_key_command_removes_a_secret(monkeypatch):
    CredentialStore(secrets_file(), environ={}).set("claude", "sk-velha")

    assert cli.main(["chave", "claude", "--remover"]) == 0

    assert CredentialStore(secrets_file(), environ={}).get("claude") is None


def test_text_mode_without_key_fails_with_instructions(capsys):
    assert cli.main(["texto"]) == 2

    assert "cubo chave gemini" in capsys.readouterr().err


def end_of_input(_prompt):
    raise EOFError


def test_text_mode_imports_legacy_env_on_first_run(monkeypatch, capsys):
    Path(".env").write_text('GEMINI_API_KEY="AIza-legado"\n')
    monkeypatch.setattr("builtins.input", end_of_input)

    assert cli.main(["texto"]) == 0

    assert load_config(default_config_dir() / "config.toml").home_assistant.devices
    output = capsys.readouterr().out
    assert "importada" in output
    # Os dispositivos vieram do protótipo, mas o token do Home Assistant não estava no .env.
    assert "nenhum token do Home Assistant" in output


def test_text_mode_conversation(monkeypatch, capsys):
    assistant = Assistant(
        provider=FakeProvider(text="Olá, tudo certo!"),
        tools=ToolRegistry(),
        memory=ConversationMemory(max_exchanges=5, idle_timeout_seconds=600),
        system_prompt="",
    )
    monkeypatch.setattr(cli, "build_runtime", lambda *_: Runtime(assistant=assistant))
    lines = iter(["oi", "   "])

    def fake_input(_prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)

    assert cli.main(["texto"]) == 0

    assert "cubô> Olá, tudo certo!" in capsys.readouterr().out


def test_voice_is_the_default_mode(monkeypatch):
    monkeypatch.setattr(cli, "_run_voice_mode", lambda *_: 7)

    assert cli.main([]) == 7


class FakeSession:
    """Sessão de voz falsa, que fala assim que é ligada."""

    warnings = ["voz reserva"]
    stopped = False

    def __init__(self, _settings, _assistant, _data_dir, on_event):
        self.on_event = on_event
        self.error = None
        self.running = True

    def start(self):
        self.on_event(Heard("que horas são"))
        self.on_event(Replied("São três da tarde."))

    def stop(self):
        FakeSession.stopped = True


def configure_gemini_key():
    CredentialStore(secrets_file(), environ={}).set("gemini", "AIza-teste-1234")


def test_voice_without_models_points_to_prepare(capsys):
    configure_gemini_key()

    assert cli.main(["--sem-painel"]) == 2

    assert "cubo preparar" in capsys.readouterr().err


def test_voice_without_panel_prints_the_conversation(monkeypatch, capsys):
    configure_gemini_key()
    FakeSession.stopped = False
    monkeypatch.setattr("cubo.voice.session.VoiceSession", FakeSession)
    monkeypatch.setattr(cli, "_wait_until_interrupted", lambda: None)

    assert cli.main(["--sem-painel"]) == 0

    output = capsys.readouterr().out
    assert "Aviso: voz reserva" in output
    assert "você> que horas são" in output
    assert "cubô> São três da tarde." in output
    assert FakeSession.stopped


def test_default_mode_runs_voice_and_the_panel(monkeypatch):
    configure_gemini_key()
    FakeSession.stopped = False
    monkeypatch.setattr("cubo.voice.session.VoiceSession", FakeSession)
    shown = []
    monkeypatch.setattr(cli, "_run_panel", lambda service, config_dir: shown.append(service))

    assert cli.main([]) == 0

    assert shown[0].voice_enabled
    assert shown[0].voice is not None
    assert FakeSession.stopped


def test_panel_command_runs_without_voice(monkeypatch):
    shown = []
    monkeypatch.setattr(cli, "_run_panel", lambda service, config_dir: shown.append(service))

    assert cli.main(["painel"]) == 0

    assert not shown[0].voice_enabled
    assert "ia" in shown[0].problems


def test_nothing_to_run_without_voice_and_without_panel(capsys):
    assert cli.main(["--sem-painel", "painel"]) == 2

    assert "Erro" in capsys.readouterr().err


def test_prepare_downloads_what_the_config_asks_for(monkeypatch, capsys):
    downloads = []
    monkeypatch.setattr(
        models, "download_wake_word", lambda name, data_dir, _http: downloads.append(("wake", name))
    )
    monkeypatch.setattr(
        models, "download_piper_voice", lambda voice, data_dir: downloads.append(("voz", voice))
    )
    monkeypatch.setattr(
        models, "download_whisper", lambda model, data_dir: downloads.append(("whisper", model))
    )

    assert cli.main(["preparar"]) == 0

    assert downloads == [
        ("wake", "hey_jarvis"),
        ("voz", "pt_BR-faber-medium"),
        ("whisper", "base"),
    ]
    assert "Tudo pronto" in capsys.readouterr().out


def test_prepare_reports_a_failed_download(monkeypatch, capsys):
    def offline(*_args):
        raise DownloadError("sem rede")

    monkeypatch.setattr(models, "download_wake_word", offline)

    assert cli.main(["preparar"]) == 1

    assert "sem rede" in capsys.readouterr().err


def test_audio_lists_the_devices(monkeypatch, capsys):
    devices = [
        SimpleNamespace(index=0, name="Microfone USB", inputs=1, outputs=0),
        SimpleNamespace(index=1, name="Placa de som", inputs=2, outputs=2),
    ]
    monkeypatch.setattr(cli, "load_devices", lambda: SimpleNamespace(list_devices=lambda: devices))

    assert cli.main(["audio"]) == 0

    output = capsys.readouterr().out
    assert "Microfone USB (entrada)" in output
    assert "Placa de som (entrada, saída)" in output
    assert "config.toml" in output
    assert "os números mudam" in output


def test_audio_without_portaudio_explains(monkeypatch, capsys):
    def missing():
        raise SetupError("Falta a biblioteca PortAudio.")

    monkeypatch.setattr(cli, "load_devices", missing)

    assert cli.main(["audio"]) == 2

    assert "PortAudio" in capsys.readouterr().err


def test_password_reset_erases_the_panel_password(capsys):
    from cubo.web.auth import AUTH_FILE_NAME, PanelAuth

    auth = PanelAuth(default_config_dir() / AUTH_FILE_NAME)
    auth.set_password("senha-segura-123")

    assert cli.main(["senha", "--redefinir"]) == 0

    assert not auth.has_password
    assert "apagada" in capsys.readouterr().out


def test_password_reset_without_a_password_says_so(capsys):
    assert cli.main(["senha", "--redefinir"]) == 0

    assert "ainda não tem senha" in capsys.readouterr().out


def test_password_command_needs_the_flag():
    with pytest.raises(SystemExit):
        cli.main(["senha"])


def test_waiting_ends_on_sigterm_and_restores_the_previous_handler():
    calls = []
    previous = signal.signal(signal.SIGTERM, lambda *_: calls.append("padrão"))
    # Se o tratamento sumir, o SIGINT de segurança encerra a espera e o teste falha em `calls`.
    timers = [
        threading.Timer(0.2, os.kill, args=(os.getpid(), signal.SIGTERM)),
        threading.Timer(3.0, os.kill, args=(os.getpid(), signal.SIGINT)),
    ]
    try:
        for timer in timers:
            timer.start()
        cli._wait_until_interrupted()
        assert calls == []
        # Quem estava instalado antes volta ao lugar depois da espera.
        os.kill(os.getpid(), signal.SIGTERM)
        assert calls == ["padrão"]
    finally:
        for timer in timers:
            timer.cancel()
        signal.signal(signal.SIGTERM, previous)
