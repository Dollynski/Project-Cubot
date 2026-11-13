"""Importa a configuração do protótipo antigo, que ficava num arquivo ``.env``."""

from pathlib import Path

from dotenv import dotenv_values

from cubo.config import Config, Device, HomeAssistantSettings, VoiceSettings
from cubo.credentials import CredentialStore

# Entidades que o protótipo usava fixas no código.
LEGACY_DEVICES = (
    Device(entity_id="input_boolean.lampada_led", alias="luz do quarto"),
    Device(entity_id="weather.forecast_home", alias="previsão do tempo"),
)


def migrate_legacy_env(env_path: Path, credentials: CredentialStore) -> tuple[Config, list[str]]:
    """Cria a configuração a partir do ``.env`` antigo.

    As chaves vão para o ``CredentialStore``; o resto vai para a ``Config`` retornada.
    Também retorna a lista do que foi importado, para mostrar ao usuário.
    """
    values = {key: value for key, value in dotenv_values(env_path).items() if value}
    imported: list[str] = []

    if gemini_key := values.get("GEMINI_API_KEY"):
        credentials.set("gemini", gemini_key)
        imported.append("chave do Gemini")
    if ha_token := values.get("HOME_ASSISTANT_TOKEN"):
        credentials.set("home_assistant", ha_token)
        imported.append("token do Home Assistant")

    home_assistant = HomeAssistantSettings(devices=list(LEGACY_DEVICES))
    imported.append("dispositivos do protótipo (luz do quarto e previsão do tempo)")
    if ha_url := values.get("HOME_ASSISTANT_URL"):
        home_assistant.url = ha_url
        imported.append("endereço do Home Assistant")

    voice = VoiceSettings()
    if microphone := values.get("MIC_DEVICE_INDEX", "").strip():
        voice.input_device = microphone
        imported.append("microfone")

    return Config(home_assistant=home_assistant, voice=voice), imported
