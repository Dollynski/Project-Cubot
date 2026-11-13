"""Voz e fala: palavra de ativação, escuta, transcrição e a voz do Cubô."""

from nicegui import run, ui
from pydantic import ValidationError

from cubo.voice.models import DownloadError, missing_models, prepare_models
from cubo.web.forms import apply_config, confirm, first_error, updated
from cubo.web.layout import section
from cubo.web.panel import Panel

CUSTOM_WAKE_WORD = "personalizada"
WAKE_WORDS = {
    "hey_jarvis": "Hey Jarvis",
    "hey_livekit": "Hey LiveKit",
    CUSTOM_WAKE_WORD: "Outro modelo (arquivo .onnx)",
}
WHISPER_MODELS = {
    "tiny": "tiny (mais rápido, erra mais)",
    "base": "base",
    "small": "small (mais preciso, mais lento)",
    "medium": "medium (o mais preciso, pesado)",
}
COMPUTE_TYPES = ["int8", "float32"]
PIPER_VOICES = [
    "pt_BR-faber-medium",
    "pt_BR-cadu-medium",
    "pt_BR-jeff-medium",
    "pt_BR-edresson-low",
]


def build(panel: Panel) -> None:
    service = panel.service
    voice = service.config.voice
    ready_made = voice.wake_word in WAKE_WORDS
    chosen_wake_word = voice.wake_word if ready_made else CUSTOM_WAKE_WORD

    async def save() -> None:
        wake_word = (
            custom_path.value.strip()
            if wake_word_select.value == CUSTOM_WAKE_WORD
            else wake_word_select.value
        )
        try:
            new = updated(
                service.config,
                voice={
                    "wake_word": wake_word,
                    "wake_word_threshold": threshold.value,
                    "silence_seconds": silence.value,
                    "max_listening_seconds": max_listening.value,
                    "whisper_model": whisper_select.value,
                    "whisper_compute_type": compute_select.value,
                    "piper_voice": voice_select.value,
                    "speech_speed": speed.value,
                },
            )
        except ValidationError as error:
            ui.notify(first_error(error), type="negative")
            return
        if not await download_missing(new):
            return
        await apply_config(service, new)

    async def download_missing(new) -> bool:
        missing = await run.io_bound(missing_models, new.voice, service.data_dir)
        if not missing:
            return True
        names = "; ".join(missing)
        if not await confirm(f"Faltam estes modelos: {names}. Baixar agora?", "Baixar"):
            return False
        notice = ui.notification("Baixando os modelos...", spinner=True, timeout=None)
        try:
            await run.io_bound(prepare_models, new.voice, service.data_dir)
        except DownloadError as error:
            ui.notify(str(error), type="negative", multi_line=True)
            return False
        finally:
            notice.dismiss()
        return True

    async def speak_sample() -> None:
        session = service.voice
        if session is None:
            ui.notify("A voz está desligada.", type="warning")
            return
        await run.io_bound(session.say, "Olá! Eu sou o Cubô. Como posso ajudar?")

    with section("Palavra de ativação", "O que você diz para chamar o Cubô."):
        wake_word_select = ui.select(WAKE_WORDS, value=chosen_wake_word, label="Palavra").classes(
            "w-full"
        )
        custom_path = ui.input(
            "Caminho do arquivo .onnx", value="" if ready_made else voice.wake_word
        ).classes("w-full")
        custom_path.bind_visibility_from(wake_word_select, "value", value=CUSTOM_WAKE_WORD)
        ui.label("Sensibilidade: mais alta ativa com mais facilidade, mas erra mais.").classes(
            "text-sm opacity-70"
        )
        threshold = ui.slider(min=0.1, max=0.9, step=0.05, value=voice.wake_word_threshold)
        ui.label().bind_text_from(threshold, "value", lambda value: f"Limite: {value:.2f}")
    with section("Escuta"):
        silence = ui.number(
            "Silêncio que encerra o pedido (segundos)",
            value=voice.silence_seconds,
            min=0.2,
            max=5,
            step=0.1,
        ).classes("w-full")
        max_listening = ui.number(
            "Duração máxima de um pedido (segundos)",
            value=voice.max_listening_seconds,
            min=3,
            max=120,
            step=1,
        ).classes("w-full")
    with section("Transcrição", "Converte o que você disse em texto."):
        whisper_select = ui.select(
            WHISPER_MODELS, value=voice.whisper_model, label="Modelo do Whisper"
        ).classes("w-full")
        compute_select = ui.select(
            COMPUTE_TYPES, value=voice.whisper_compute_type, label="Precisão"
        ).classes("w-full")
    with section("Voz do Cubô"):
        voice_select = ui.select(
            PIPER_VOICES,
            value=voice.piper_voice,
            label="Voz do Piper",
            with_input=True,
            new_value_mode="add-unique",
        ).classes("w-full")
        speed = ui.slider(min=0.5, max=2.0, step=0.05, value=voice.speech_speed)
        ui.label().bind_text_from(speed, "value", lambda value: f"Velocidade: {value:.2f}x")
        ui.button("Ouvir a voz salva", icon="volume_up", on_click=speak_sample).props("outline")
    ui.button("Salvar", icon="save", on_click=save)
