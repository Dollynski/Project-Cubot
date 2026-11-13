"""IA: provedor, modelo, chave de API, personalidade, memória e limites de uso."""

from nicegui import run, ui
from pydantic import ValidationError

from cubo.config import ProviderName
from cubo.llm.base import ProviderError
from cubo.llm.factory import DISPLAY_NAMES, list_provider_models
from cubo.web.forms import apply_config, first_error, secret_field, updated
from cubo.web.layout import section
from cubo.web.panel import Panel
from cubo.web.widgets import usage_summary

PROVIDERS = {
    "gemini": "Gemini (Google)",
    "claude": "Claude (Anthropic)",
    "openai": "OpenAI",
    "ollama": "Ollama (neste aparelho ou na rede)",
}


def build(panel: Panel) -> None:
    service = panel.service
    llm = service.config.llm
    found_models: dict[str, list[str]] = {}
    fields: dict[str, ui.element] = {}

    def ollama_url() -> str:
        field = fields.get("ollama_url")
        return field.value.strip() if field else llm.ollama_url

    async def search_models(name: ProviderName, api_key: str) -> list[str] | None:
        try:
            return sorted(
                await run.io_bound(
                    list_provider_models, name, api_key=api_key, ollama_url=ollama_url()
                )
            )
        except ProviderError as error:
            ui.notify(error.user_message, type="negative", multi_line=True)
            return None

    async def refresh_models() -> None:
        name = provider.value
        api_key = "" if name == "ollama" else (service.credentials.get(name) or "")
        if name != "ollama" and not api_key:
            ui.notify("Salve a chave antes de buscar os modelos.", type="warning")
            return
        if (models := await search_models(name, api_key)) is not None:
            found_models[name] = models
            provider_settings.refresh()

    async def save_key() -> None:
        name = provider.value
        typed = fields["key"].value.strip()
        if not typed:
            ui.notify("Digite a chave para salvar.", type="warning")
            return
        if (models := await search_models(name, typed)) is None:
            return
        await run.io_bound(service.save_credential, name, typed)
        found_models[name] = models
        ui.notify(f"Chave válida e salva. {len(models)} modelos disponíveis.", type="positive")
        provider_settings.refresh()

    async def remove_key() -> None:
        await run.io_bound(service.delete_credential, provider.value)
        ui.notify("Chave removida.")
        provider_settings.refresh()

    async def save() -> None:
        name = provider.value
        models = {**service.config.llm.models.model_dump(), name: fields["model"].value or ""}
        try:
            new = updated(
                service.config,
                llm={
                    "provider": name,
                    "models": models,
                    "ollama_url": ollama_url(),
                    "personality": personality.value,
                    "memory_exchanges": int(memory_exchanges.value or 0),
                    "memory_idle_minutes": int(memory_idle.value or 0),
                    "max_calls_per_minute": int(per_minute.value or 0),
                    "max_calls_per_day": int(per_day.value or 0),
                },
            )
        except ValidationError as error:
            ui.notify(first_error(error), type="negative")
            return
        await apply_config(service, new)

    with section("Provedor de IA"):
        provider = ui.select(
            PROVIDERS,
            value=llm.provider,
            label="Provedor",
            on_change=lambda: provider_settings.refresh(),
        ).classes("w-full")

        @ui.refreshable
        def provider_settings() -> None:
            name: ProviderName = provider.value
            if name == "ollama":
                fields["ollama_url"] = ui.input("Endereço do Ollama", value=llm.ollama_url).classes(
                    "w-full"
                )
            else:
                label = f"Chave de API do {DISPLAY_NAMES[name]}"
                fields["key"] = secret_field(label, service.credentials.masked(name))
                with ui.row():
                    ui.button("Validar e salvar a chave", icon="key", on_click=save_key)
                    if service.credentials.get(name):
                        ui.button("Remover", on_click=remove_key).props("flat color=negative")
            current = getattr(service.config.llm.models, name)
            options = found_models.get(name) or ([current] if current else [])
            if current and current not in options:
                options = [current, *options]
            fields["model"] = ui.select(
                options,
                value=current or None,
                label="Modelo",
                with_input=True,
                new_value_mode="add-unique",
            ).classes("w-full")
            ui.button("Buscar modelos disponíveis", on_click=refresh_models).props("flat")

        provider_settings()
    with section("Personalidade", "Como o Cubô se comporta e fala."):
        personality = ui.textarea(value=llm.personality).props("autogrow").classes("w-full")
    with section("Memória da conversa"):
        memory_exchanges = ui.number(
            "Quantas trocas lembrar", value=llm.memory_exchanges, min=1, max=100, step=1
        ).classes("w-full")
        memory_idle = ui.number(
            "Esquecer depois de (minutos sem falar)", value=llm.memory_idle_minutes, min=1, step=1
        ).classes("w-full")
    with section("Limites de uso", "Freio de custo. Zero desliga o limite."):
        per_minute = ui.number(
            "Chamadas por minuto", value=llm.max_calls_per_minute, min=0, step=1
        ).classes("w-full")
        per_day = ui.number("Chamadas por dia", value=llm.max_calls_per_day, min=0, step=1).classes(
            "w-full"
        )

        @ui.refreshable
        def usage() -> None:
            usage_summary(service)

        usage()
    ui.button("Salvar", icon="save", on_click=save)
    ui.timer(10.0, usage.refresh)
