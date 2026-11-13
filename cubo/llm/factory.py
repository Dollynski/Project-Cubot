"""Cria o provedor de IA escolhido na configuração."""

from cubo.config import LLMSettings, ProviderName
from cubo.credentials import ENV_VARS, CredentialName, CredentialStore
from cubo.errors import SetupError
from cubo.llm.base import ChatProvider

DISPLAY_NAMES: dict[ProviderName, str] = {
    "gemini": "Gemini",
    "claude": "Claude",
    "openai": "OpenAI",
    "ollama": "Ollama",
}

# O Ollama ignora a chave, mas o SDK da OpenAI exige uma.
_OLLAMA_PLACEHOLDER_KEY = "ollama"


def create_provider(settings: LLMSettings, credentials: CredentialStore) -> ChatProvider:
    # Cada SDK é importado só quando é o escolhido: carregar os três atrasaria a inicialização.
    provider, model = settings.provider, settings.model
    if not model:
        raise SetupError(
            f"Nenhum modelo escolhido para {DISPLAY_NAMES[provider]}. "
            f"Preencha llm.models.{provider} no config.toml."
        )
    match provider:
        case "gemini":
            from cubo.llm.gemini import GeminiProvider

            return GeminiProvider(api_key=_required_key(credentials, "gemini"), model=model)
        case "claude":
            from cubo.llm.claude import ClaudeProvider

            return ClaudeProvider(api_key=_required_key(credentials, "claude"), model=model)
        case "openai":
            from cubo.llm.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                name="openai",
                display_name=DISPLAY_NAMES["openai"],
                api_key=_required_key(credentials, "openai"),
                model=model,
            )
        case "ollama":
            from cubo.llm.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                name="ollama",
                display_name=DISPLAY_NAMES["ollama"],
                api_key=_OLLAMA_PLACEHOLDER_KEY,
                model=model,
                base_url=settings.ollama_url,
            )
        case _:
            raise SetupError(f"Provedor desconhecido: {provider}")


def _required_key(credentials: CredentialStore, name: CredentialName) -> str:
    key = credentials.get(name)
    if not key:
        raise SetupError(
            f"Nenhuma chave de API configurada para {DISPLAY_NAMES[name]}. "
            f"Rode `cubo chave {name}` ou defina a variável {ENV_VARS[name]}."
        )
    return key
