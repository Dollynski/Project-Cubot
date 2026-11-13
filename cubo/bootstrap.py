"""Monta o assistente a partir da configuração."""

from dataclasses import dataclass, field

from cubo.assistant import Assistant
from cubo.config import Config, Device
from cubo.credentials import CredentialStore
from cubo.llm.factory import create_provider
from cubo.llm.memory import ConversationMemory
from cubo.llm.prompts import build_system_prompt
from cubo.tools.home_assistant import HomeAssistantClient, HomeAssistantTools
from cubo.tools.registry import Tool, ToolRegistry


@dataclass
class Runtime:
    assistant: Assistant
    home_assistant: HomeAssistantClient | None = None
    warnings: list[str] = field(default_factory=list)

    def close(self) -> None:
        if self.home_assistant is not None:
            self.home_assistant.close()


def build_runtime(config: Config, credentials: CredentialStore) -> Runtime:
    """Cria o assistente. Levanta ``SetupError`` se faltar algo essencial, como a chave da IA."""
    provider = create_provider(config.llm, credentials)

    warnings: list[str] = []
    client: HomeAssistantClient | None = None
    tools: list[Tool] = []
    devices: list[Device] = []
    home = config.home_assistant
    token = credentials.get("home_assistant")
    if home.devices and token:
        client = HomeAssistantClient(home.url, token)
        tools = HomeAssistantTools(client, home.devices).build()
        devices = home.devices
    elif home.devices:
        warnings.append(
            "Há dispositivos cadastrados, mas nenhum token do Home Assistant. "
            "Rode `cubo chave home_assistant`."
        )

    memory = ConversationMemory(
        max_exchanges=config.llm.memory_exchanges,
        idle_timeout_seconds=config.llm.memory_idle_minutes * 60,
    )
    assistant = Assistant(
        provider=provider,
        tools=ToolRegistry(tools),
        memory=memory,
        system_prompt=build_system_prompt(config.llm.personality, devices),
    )
    return Runtime(assistant=assistant, home_assistant=client, warnings=warnings)
