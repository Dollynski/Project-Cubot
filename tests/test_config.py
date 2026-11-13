import pytest
from pydantic import ValidationError

from cubo.config import (
    Config,
    Device,
    HomeAssistantSettings,
    VoiceSettings,
    load_config,
    save_config,
)
from cubo.credentials import CredentialStore
from cubo.migration import LEGACY_DEVICES, migrate_legacy_env


def test_missing_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / "config.toml")

    assert config.llm.provider == "gemini"
    assert config.llm.model == "gemini-3.5-flash"
    assert config.home_assistant.devices == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    config = Config()
    config.llm.provider = "claude"
    config.home_assistant.devices = [Device(entity_id="light.sala", alias="luz da sala")]

    save_config(config, path)

    assert load_config(path) == config
    assert load_config(path).llm.model == "claude-opus-5-5"


def test_voice_settings_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    config = Config()
    config.voice.wake_word = "hey_livekit"
    config.voice.input_device = "USB"

    save_config(config, path)

    assert load_config(path).voice == config.voice


@pytest.mark.parametrize(
    "field, value",
    [
        ("wake_word_threshold", 0),
        ("wake_word_threshold", 1),
        ("silence_seconds", 0),
        ("max_listening_seconds", -1),
        ("speech_speed", 3),
    ],
)
def test_rejects_out_of_range_voice_settings(field, value):
    with pytest.raises(ValidationError):
        VoiceSettings(**{field: value})


def test_device_domain():
    assert Device(entity_id="input_boolean.lampada_led", alias="luz").domain == "input_boolean"


def test_rejects_invalid_entity_id():
    with pytest.raises(ValidationError):
        Device(entity_id="Luz da Sala", alias="luz")


def test_rejects_repeated_aliases_ignoring_case():
    with pytest.raises(ValidationError, match="apelidos repetidos"):
        HomeAssistantSettings(
            devices=[
                Device(entity_id="light.sala", alias="Luz"),
                Device(entity_id="light.quarto", alias="luz"),
            ]
        )


def test_migrates_legacy_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        'GEMINI_API_KEY="AIza-legado"\n'
        'HOME_ASSISTANT_URL="http://192.168.0.10:8123"\n'
        'HOME_ASSISTANT_TOKEN="token-legado"\n'
        "MIC_DEVICE_INDEX=1\n"
    )
    credentials = CredentialStore(tmp_path / "secrets.toml", environ={})

    config, imported = migrate_legacy_env(env, credentials)

    assert credentials.get("gemini") == "AIza-legado"
    assert credentials.get("home_assistant") == "token-legado"
    assert config.home_assistant.url == "http://192.168.0.10:8123"
    assert config.home_assistant.devices == list(LEGACY_DEVICES)
    assert config.voice.input_device == "1"
    assert "chave do Gemini" in imported
    assert "microfone" in imported


def test_migration_skips_empty_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text('GEMINI_API_KEY=""\n')
    credentials = CredentialStore(tmp_path / "secrets.toml", environ={})

    config, imported = migrate_legacy_env(env, credentials)

    assert credentials.get("gemini") is None
    assert config.home_assistant.url == "http://localhost:8123"
    assert config.voice.input_device == ""
    assert "chave do Gemini" not in imported
    assert "microfone" not in imported
