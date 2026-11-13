import stat
from pathlib import Path

import cubo.__main__ as cli
from cubo.assistant import Assistant
from cubo.bootstrap import Runtime
from cubo.config import default_config_dir, load_config
from cubo.credentials import CredentialStore
from cubo.llm.memory import ConversationMemory
from cubo.tools.registry import ToolRegistry
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
