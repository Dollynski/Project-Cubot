"""Sessão de voz: o ciclo rodando numa thread, com as peças trocáveis uma a uma."""

import logging
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

from cubo.config import VoiceSettings
from cubo.errors import SetupError
from cubo.voice import load_devices
from cubo.voice.builder import load_synthesizer, load_transcriber, load_wake_word, parse_device
from cubo.voice.events import Event
from cubo.voice.listening import ListeningLimits, SpeechDetector, UtteranceRecorder
from cubo.voice.loop import Replier, VoiceLoop
from cubo.voice.tts import Speaker

logger = logging.getLogger(__name__)

STOP_TIMEOUT_SECONDS = 10.0
# Quanto esperar um pedido em andamento terminar antes de trocar o microfone.
SWAP_WAIT_SECONDS = 120.0


class Part(StrEnum):
    """Peças que a configuração de voz alimenta. O valor é o nome mostrado ao usuário."""

    WAKE_WORD = "palavra de ativação"
    TRANSCRIBER = "transcrição"
    VOICE = "voz"
    RECORDER = "gravação"
    OUTPUT = "alto-falante"
    INPUT = "microfone"


# Se nenhuma configuração de uma peça mudou, a peça fica como está.
PART_SETTINGS: dict[Part, tuple[str, ...]] = {
    Part.WAKE_WORD: ("wake_word", "wake_word_threshold"),
    Part.TRANSCRIBER: ("whisper_model", "whisper_compute_type"),
    Part.VOICE: ("piper_voice", "speech_speed"),
    Part.RECORDER: ("silence_seconds", "max_listening_seconds"),
    Part.OUTPUT: ("output_device",),
    Part.INPUT: ("input_device",),
}


class VoiceSession:
    """Monta o ciclo de voz e o mantém rodando, atualizando só a peça cuja configuração mudou."""

    def __init__(
        self,
        settings: VoiceSettings,
        assistant: Replier,
        data_dir: Path,
        on_event: Callable[[Event], None] = lambda _event: None,
    ) -> None:
        """Carrega os modelos e prepara os dispositivos. Levanta ``SetupError`` se algo faltar."""
        self._settings = settings
        self._data_dir = data_dir
        self.warnings: list[str] = []
        self.error: str | None = None  # por que o ciclo parou, se ele caiu

        # Primeiro os modelos, para a falta deles ser avisada antes de qualquer problema de áudio.
        wake_word = load_wake_word(settings, data_dir)
        transcriber = load_transcriber(settings, data_dir)
        self._synthesizer = load_synthesizer(settings, data_dir, self.warnings)
        devices = load_devices()
        self._detector = SpeechDetector()
        self._player = devices.SoundDevicePlayer(parse_device(settings.output_device))
        self._speaker = Speaker(self._synthesizer, self._player)
        self._microphone = devices.Microphone(parse_device(settings.input_device))
        self._loop = VoiceLoop(
            microphone=self._microphone,
            wake_word=wake_word,
            recorder=self._recorder_for(settings),
            transcriber=transcriber,
            assistant=assistant,
            speaker=self._speaker,
            on_event=on_event,
            stream_speech=settings.stream_speech,
        )
        self._warm_up(self._detector, wake_word, transcriber, self._speaker)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def settings(self) -> VoiceSettings:
        return self._settings

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def mic_level(self) -> float:
        return self._loop.mic_level

    def start(self) -> None:
        """Abre o microfone e começa a escutar. Levanta ``SetupError`` se ele não abrir."""
        if self.running:
            return
        self.error = None
        # A thread leva o microfone e o sinal de parada que são dela: se eles forem trocados
        # depois, ela continua fechando e obedecendo os seus, e não os da thread nova.
        stop, microphone = threading.Event(), self._microphone
        microphone.open()
        self._stop = stop
        self._thread = threading.Thread(
            target=self._run, args=(microphone, stop), name="cubo-voz", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is None:
            return
        self._thread.join(STOP_TIMEOUT_SECONDS)
        if self._thread.is_alive():
            logger.warning("O ciclo de voz ainda não parou: terminando o pedido em andamento")
        else:
            self._thread = None

    def set_assistant(self, assistant: Replier) -> None:
        self._loop.replace(assistant=assistant)

    def say(self, text: str) -> None:
        """Fala o texto pelo alto-falante e só retorna quando terminar de falar."""
        self._speaker.say(text)

    def beep(self) -> None:
        self._speaker.chime()

    def reconfigure(self, new: VoiceSettings) -> list[str]:
        """Aplica uma nova configuração trocando só as peças afetadas.

        Tudo o que mudou é carregado antes de qualquer troca, então uma falha (modelo ausente,
        dispositivo inexistente) deixa a sessão como estava. Retorna o nome do que foi trocado.
        """
        changed = {
            part
            for part, fields in PART_SETTINGS.items()
            if any(getattr(self._settings, field) != getattr(new, field) for field in fields)
        }
        parts: dict[str, Any] = {}
        synthesizer, player, microphone = self._synthesizer, self._player, None
        devices = load_devices() if changed & {Part.INPUT, Part.OUTPUT} else None

        if Part.WAKE_WORD in changed:
            parts["wake_word"] = load_wake_word(new, self._data_dir)
        if Part.TRANSCRIBER in changed:
            parts["transcriber"] = load_transcriber(new, self._data_dir)
        if Part.RECORDER in changed:
            parts["recorder"] = self._recorder_for(new)
        if Part.VOICE in changed:
            synthesizer = load_synthesizer(new, self._data_dir, self.warnings)
        if Part.OUTPUT in changed:
            player = devices.SoundDevicePlayer(parse_device(new.output_device))
        if Part.VOICE in changed or Part.OUTPUT in changed:
            parts["speaker"] = Speaker(synthesizer, player)
        if Part.INPUT in changed:
            microphone = devices.Microphone(parse_device(new.input_device))

        # Aquece só o que é novo, antes de trocar: o primeiro pedido depois de salvar não demora.
        self._warm_up(*parts.values())
        if microphone is not None:
            # Primeiro o microfone, que é o único que pode falhar na troca: assim, se ele falhar,
            # nenhuma outra peça foi trocada.
            self._swap_microphone(microphone)
        self._loop.replace(**parts)
        self._loop.stream_speech = new.stream_speech
        if "speaker" in parts:
            self._synthesizer, self._player, self._speaker = synthesizer, player, parts["speaker"]
        self._settings = new
        return [part.value for part in Part if part in changed]

    def _swap_microphone(self, microphone: Any) -> None:
        """Troca o microfone esperando o ciclo atual terminar de verdade.

        Se o novo não abrir, volta a escutar pelo antigo e levanta ``SetupError``.
        """
        was_running = self.running
        self._stop_and_wait()
        previous = self._microphone
        self._use_microphone(microphone)
        if not was_running:
            return
        try:
            self.start()
        except SetupError:
            self._use_microphone(previous)
            try:
                self.start()
            except SetupError:
                logger.exception("Não consegui voltar ao microfone anterior")
            raise

    def _stop_and_wait(self) -> None:
        """Para o ciclo e espera a thread acabar, mesmo que um pedido longo esteja em andamento.

        Duas threads nunca rodam juntas no mesmo ciclo: uma delas atrapalharia a outra.
        """
        self.stop()
        thread = self._thread
        if thread is None:
            return
        logger.info("Esperando o pedido em andamento terminar para trocar o microfone")
        thread.join(SWAP_WAIT_SECONDS)
        if thread.is_alive():
            raise SetupError(
                "O Cubô ainda está terminando um pedido e não deu para trocar o microfone agora. "
                "A voz desliga quando ele terminar: ligue de novo pela página Início."
            )
        self._thread = None

    def _use_microphone(self, microphone: Any) -> None:
        self._microphone = microphone
        self._loop.replace(microphone=microphone)

    @staticmethod
    def _warm_up(*parts: Any) -> None:
        """Roda uma vez cada peça que sabe se aquecer (as outras, como o gravador, não precisam)."""
        for part in parts:
            if hasattr(part, "warm_up"):
                started = time.monotonic()
                part.warm_up()
                logger.debug(
                    "Aquecimento de %s: %.2f s", type(part).__name__, time.monotonic() - started
                )

    def _recorder_for(self, settings: VoiceSettings) -> UtteranceRecorder:
        limits = ListeningLimits(
            silence_seconds=settings.silence_seconds, max_seconds=settings.max_listening_seconds
        )
        return UtteranceRecorder(self._detector, limits)

    def _run(self, microphone: Any, stop: threading.Event) -> None:
        try:
            self._loop.run(stop)
        except Exception as error:
            logger.exception("O ciclo de voz parou")
            self.error = str(error) or type(error).__name__
        finally:
            microphone.close()
