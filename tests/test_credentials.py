import stat

import pytest

from cubo.credentials import CredentialStore


@pytest.fixture
def secrets_path(tmp_path):
    return tmp_path / "cubo" / "secrets.toml"


def test_set_creates_private_file(secrets_path):
    CredentialStore(secrets_path, environ={}).set("gemini", "AIza-segredo-1234")

    assert stat.S_IMODE(secrets_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(secrets_path.parent.stat().st_mode) == 0o700


def test_get_reads_back_from_a_new_instance(secrets_path):
    CredentialStore(secrets_path, environ={}).set("claude", "  sk-ant-chave  ")

    assert CredentialStore(secrets_path, environ={}).get("claude") == "sk-ant-chave"


def test_environment_variable_has_priority(secrets_path):
    store = CredentialStore(secrets_path, environ={"OPENAI_API_KEY": "sk-do-ambiente"})
    store.set("openai", "sk-do-arquivo")

    assert store.get("openai") == "sk-do-ambiente"


def test_delete(secrets_path):
    store = CredentialStore(secrets_path, environ={})
    store.set("home_assistant", "token-longo")

    assert store.delete("home_assistant") is True
    assert store.get("home_assistant") is None
    assert store.delete("home_assistant") is False


def test_masked_shows_only_last_four_characters(secrets_path):
    store = CredentialStore(secrets_path, environ={})
    store.set("gemini", "AIzaSyExemplo9876")

    assert store.masked("gemini") == "••••9876"
    assert store.masked("claude") is None


def test_all_values_includes_file_and_environment(secrets_path):
    store = CredentialStore(secrets_path, environ={"ANTHROPIC_API_KEY": "sk-ambiente"})
    store.set("gemini", "AIza-arquivo")

    assert sorted(store.all_values()) == ["AIza-arquivo", "sk-ambiente"]


def test_rejects_unknown_name_and_empty_value(secrets_path):
    store = CredentialStore(secrets_path, environ={})

    with pytest.raises(ValueError, match="desconhecida"):
        store.set("github", "x")
    with pytest.raises(ValueError, match="vazia"):
        store.set("gemini", "   ")
