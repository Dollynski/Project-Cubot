"""Montagem do prompt de sistema."""

from collections.abc import Sequence

from cubo.config import Device

SPEECH_RULES = (
    "Suas respostas serão lidas em voz alta por um sintetizador. "
    "Escreva só texto corrido, em frases curtas, sem markdown, listas, emojis ou links."
)

TOOL_RULES = (
    "Use as ferramentas para controlar ou consultar os dispositivos da casa. "
    "Nunca diga que uma ação foi feita sem a confirmação da ferramenta; "
    "se ela falhar, explique o problema em poucas palavras."
)

NO_DEVICES = (
    "Nenhum dispositivo da casa está disponível. Se pedirem para controlar algo, "
    "explique que é preciso cadastrar o dispositivo e configurar o Home Assistant."
)


def build_system_prompt(personality: str, devices: Sequence[Device]) -> str:
    """Junta a personalidade, as regras de fala e os dispositivos que as ferramentas alcançam."""
    sections = [personality.strip(), SPEECH_RULES]
    if devices:
        listing = "\n".join(f"- {device.alias} ({device.entity_id})" for device in devices)
        sections += [TOOL_RULES, f"Dispositivos disponíveis:\n{listing}"]
    else:
        sections.append(NO_DEVICES)
    return "\n\n".join(sections)
