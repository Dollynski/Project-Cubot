"""Configuração do Cubô, guardada em ``config.toml`` (sem segredos)."""

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from cubo.toml_files import read_toml, write_toml

ProviderName = Literal["gemini", "claude", "openai", "ollama"]

CONFIG_FILE_NAME = "config.toml"

DEFAULT_PERSONALITY = (
    "Você é o Cubô, um assistente de voz com personalidade masculina, prestativo e amigável. "
    "Responda sempre em português do Brasil, de forma concisa, direta e informal. "
    "Responda só o que foi perguntado. "
    "Quando pedirem para você cantar, cante a música 'Daisy Bell' em inglês."
)


class ProviderModels(BaseModel):
    """Modelo escolhido para cada provedor; trocar de provedor não perde a escolha dos outros."""

    gemini: str = "gemini-3.5-flash"
    claude: str = "claude-opus-5-5"
    openai: str = ""
    ollama: str = ""


class LLMSettings(BaseModel):
    provider: ProviderName = "gemini"
    models: ProviderModels = Field(default_factory=ProviderModels)
    ollama_url: str = "http://localhost:11434/v1"
    personality: str = DEFAULT_PERSONALITY
    memory_exchanges: int = Field(default=10, ge=1, le=100)
    memory_idle_minutes: int = Field(default=10, ge=1)
    # Freio de custo: cada pedido à IA conta uma chamada. Zero desliga o limite.
    max_calls_per_minute: int = Field(default=20, ge=0)
    max_calls_per_day: int = Field(default=500, ge=0)

    @property
    def model(self) -> str:
        return getattr(self.models, self.provider)


class Device(BaseModel):
    """Entidade do Home Assistant que o Cubô pode usar, com o nome pelo qual é chamada."""

    entity_id: str = Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")
    alias: str = Field(min_length=1)

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


class HomeAssistantSettings(BaseModel):
    url: str = "http://localhost:8123"
    devices: list[Device] = Field(default_factory=list)

    @field_validator("devices")
    @classmethod
    def aliases_must_be_unique(cls, devices: list[Device]) -> list[Device]:
        aliases = [device.alias.casefold() for device in devices]
        duplicates = sorted({alias for alias in aliases if aliases.count(alias) > 1})
        if duplicates:
            raise ValueError(f"apelidos repetidos: {', '.join(duplicates)}")
        return devices


class VoiceSettings(BaseModel):
    # Vazio usa o dispositivo padrão do sistema; aceita o número ou parte do nome (`cubo audio`).
    input_device: str = ""
    output_device: str = ""
    # Modelo pronto (hey_jarvis, hey_livekit) ou caminho de um .onnx treinado.
    wake_word: str = "hey_jarvis"
    wake_word_threshold: float = Field(default=0.5, gt=0, lt=1)
    silence_seconds: float = Field(default=0.8, gt=0)
    max_listening_seconds: float = Field(default=15, gt=0)
    whisper_model: str = "base"
    whisper_compute_type: str = "int8"
    piper_voice: str = "pt_BR-faber-medium"
    speech_speed: float = Field(default=1.0, ge=0.5, le=2.0)


class PanelSettings(BaseModel):
    # "local" só atende neste aparelho; "network" atende também o resto da rede (celular, PC).
    listen: Literal["local", "network"] = "local"
    port: int = Field(default=8080, ge=1, le=65535)
    # HTTPS é opcional: informe o certificado e a chave juntos.
    ssl_certfile: str = ""
    ssl_keyfile: str = ""

    @property
    def host(self) -> str:
        return "127.0.0.1" if self.listen == "local" else "0.0.0.0"

    @property
    def https(self) -> bool:
        return bool(self.ssl_certfile)

    @model_validator(mode="after")
    def certificate_needs_key(self) -> "PanelSettings":
        if bool(self.ssl_certfile) != bool(self.ssl_keyfile):
            raise ValueError("ssl_certfile e ssl_keyfile devem ser informados juntos")
        return self


class Config(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    home_assistant: HomeAssistantSettings = Field(default_factory=HomeAssistantSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    panel: PanelSettings = Field(default_factory=PanelSettings)


def default_config_dir() -> Path:
    """Pasta de configuração: ``$CUBO_CONFIG_DIR`` ou ``$XDG_CONFIG_HOME/cubo``."""
    if override := os.environ.get("CUBO_CONFIG_DIR"):
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "cubo"


def load_config(path: Path) -> Config:
    """Lê a configuração; sem arquivo, usa os valores padrão."""
    return Config.model_validate(read_toml(path))


def save_config(config: Config, path: Path) -> None:
    write_toml(path, config.model_dump(mode="json"), mode=0o644)
