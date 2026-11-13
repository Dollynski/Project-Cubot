import pytest

from cubo.config import LLMSettings
from cubo.credentials import CredentialStore
from cubo.errors import SetupError
from cubo.llm.factory import create_provider


@pytest.fixture
def credentials(tmp_path):
    return CredentialStore(tmp_path / "secrets.toml", environ={})


@pytest.mark.parametrize("provider", ["gemini", "claude", "openai"])
def test_creates_provider_when_key_and_model_exist(provider, credentials):
    credentials.set(provider, "chave-de-teste")
    settings = LLMSettings(provider=provider)
    settings.models.openai = "modelo-openai"

    assert create_provider(settings, credentials).name == provider


def test_missing_key_explains_how_to_set_it(credentials):
    with pytest.raises(SetupError, match="cubo chave claude"):
        create_provider(LLMSettings(provider="claude"), credentials)


def test_missing_model_explains_which_field_to_fill(credentials):
    credentials.set("openai", "chave-de-teste")

    with pytest.raises(SetupError, match="llm.models.openai"):
        create_provider(LLMSettings(provider="openai"), credentials)


def test_ollama_needs_no_key_and_uses_the_configured_url(credentials):
    settings = LLMSettings(provider="ollama", ollama_url="http://placa.local:11434/v1")
    settings.models.ollama = "llama3.2"

    provider = create_provider(settings, credentials)

    assert provider.name == "ollama"
    assert str(provider._client.base_url).startswith("http://placa.local:11434/v1")
