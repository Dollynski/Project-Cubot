import stat
from pathlib import Path
from types import SimpleNamespace

import cubo.__main__ as cli
from cubo.assistant import Assistant
from cubo.bootstrap import Runtime
from cubo.config import default_config_dir, load_config
from cubo.credentials import CredentialStore
from cubo.errors import SetupError
from cubo.llm.memory import ConversationMemory
from cubo.tools.registry import ToolRegistry
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


def test_voice_mode_without_models_points_to_prepare(monkeypatch, capsys):
    assistant = Assistant(
        provider=FakeProvider(text="oi"),
        tools=ToolRegistry(),
        memory=ConversationMemory(max_exchanges=5, idle_timeout_seconds=600),
        system_prompt="",
    )
    monkeypatch.setattr(cli, "build_runtime", lambda *_: Runtime(assistant=assistant))

    assert cli.main([]) == 2

    assert "cubo preparar" in capsys.readouterr().err


def test_voice_mode_prints_the_conversation(monkeypatch, capsys):
    class FakeSession:
        warnings = ["voz reserva"]
        stopped = False

        def __init__(self, _settings, _assistant, _data_dir, on_event):
            self.on_event = on_event

        def start(self):
            self.on_event(Heard("que horas são"))
            self.on_event(Replied("São três da tarde."))

        def stop(self):
            FakeSession.stopped = True

    assistant = Assistant(
        provider=FakeProvider(text="oi"),
        tools=ToolRegistry(),
        memory=ConversationMemory(max_exchanges=5, idle_timeout_seconds=600),
        system_prompt="",
    )
    monkeypatch.setattr(cli, "build_runtime", lambda *_: Runtime(assistant=assistant))
    monkeypatch.setattr("cubo.voice.session.VoiceSession", FakeSession)
    monkeypatch.setattr(cli, "_wait_until_interrupted", lambda: None)

    assert cli.main([]) == 0

    output = capsys.readouterr().out
    assert "Aviso: voz reserva" in output
    assert "você> que horas são" in output
    assert "cubô> São três da tarde." in output
    assert FakeSession.stopped


def test_prepare_downloads_what_the_config_asks_for(monkeypatch, capsys):
    downloads = []
    monkeypatch.setattr(
        cli, "download_wake_word", lambda name, data_dir, _http: downloads.append(("wake", name))
    )
    monkeypatch.setattr(
        cli, "download_piper_voice", lambda voice, data_dir: downloads.append(("voz", voice))
    )
    monkeypatch.setattr(
        cli, "download_whisper", lambda model, data_dir: downloads.append(("whisper", model))
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

    monkeypatch.setattr(cli, "download_wake_word", offline)

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
