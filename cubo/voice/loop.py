"""O ciclo de voz: espera a wake word, escuta o pedido, responde falando."""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Protocol

import numpy as np

from cubo.voice.events import Event, Heard, Replied, State, StateChanged, Timed
from cubo.voice.listening import UtteranceRecorder
from cubo.voice.speech_stream import SpeechStream
from cubo.voice.stt import Transcriber
from cubo.voice.timing import Stopwatch
from cubo.voice.tts import Speaker
from cubo.voice.wake_word import WakeWordDetector

logger = logging.getLogger(__name__)

# Peças que podem ser trocadas. Todas valem com o ciclo rodando, menos o microfone, que alimenta
# o ciclo inteiro: ele só pode ser trocado com o ciclo parado.
REPLACEABLE_PARTS = frozenset(
    {"microphone", "wake_word", "recorder", "transcriber", "assistant", "speaker"}
)


class Replier(Protocol):
    def reply(self, user_text: str, on_text: Callable[[str], None] | None = None) -> str:
        """Responde ao que foi dito, já em texto pronto para falar."""
        ...


class Microphone(Protocol):
    def frames(self, stop: threading.Event) -> Iterator[np.ndarray]:
        """Quadros de áudio contínuos (float32, 16 kHz) até ``stop`` ser acionado."""
        ...

    def flush(self) -> None:
        """Descarta o áudio acumulado, como o que o próprio Cubô tocou."""
        ...


class VoiceLoop:
    def __init__(
        self,
        microphone: Microphone,
        wake_word: WakeWordDetector,
        recorder: UtteranceRecorder,
        transcriber: Transcriber,
        assistant: Replier,
        speaker: Speaker,
        on_event: Callable[[Event], None] = lambda _event: None,
        clock: Callable[[], float] = time.monotonic,
        stream_speech: bool = True,
    ) -> None:
        self._microphone = microphone
        self._wake_word = wake_word
        self._recorder = recorder
        self._transcriber = transcriber
        self._assistant = assistant
        self._speaker = speaker
        self._on_event = on_event
        self._clock = clock
        self.stream_speech = stream_speech
        self.mic_level = 0.0  # volume do último quadro (RMS), para o painel mostrar

    def replace(self, **parts: object) -> None:
        """Troca peças do ciclo. A troca vale a partir do próximo pedido (ou quadro de áudio)."""
        unknown = parts.keys() - REPLACEABLE_PARTS
        if unknown:
            raise ValueError(f"peças que não podem ser trocadas: {', '.join(sorted(unknown))}")
        for name, part in parts.items():
            setattr(self, f"_{name}", part)

    def run(self, stop: threading.Event) -> None:
        """Atende pedidos até ``stop`` ser acionado."""
        frames = self._measured(self._microphone.frames(stop))
        self._on_event(StateChanged(State.WAITING))
        for frame in frames:
            if self._wake_word.detected(frame):
                self._attend(frames)
                self._on_event(StateChanged(State.WAITING))

    def _measured(self, frames: Iterator[np.ndarray]) -> Iterator[np.ndarray]:
        for frame in frames:
            self.mic_level = float(np.sqrt(np.mean(np.square(frame))))
            yield frame

    def _attend(self, frames: Iterator[np.ndarray]) -> None:
        try:
            self._speaker.chime()
            self._microphone.flush()
            self._respond_to(frames)
        except Exception:
            # Um pedido com problema não pode derrubar o assistente que fica ligado o dia todo.
            logger.exception("Falha ao atender o pedido")
        finally:
            # O que o Cubô falou não pode ser ouvido como um novo pedido nem como wake word.
            self._microphone.flush()
            self._wake_word.reset()

    def _respond_to(self, frames: Iterator[np.ndarray]) -> None:
        self._on_event(StateChanged(State.LISTENING))
        audio = self._recorder.record(frames)
        if audio is None:
            return

        stopwatch = Stopwatch(self._clock)  # conta a partir do fim da gravação
        self._on_event(StateChanged(State.TRANSCRIBING))
        text = self._transcriber.transcribe(audio)
        stopwatch.mark("transcribed")
        if not text:
            return
        self._on_event(Heard(text))

        self._on_event(StateChanged(State.THINKING))
        self._answer(text, stopwatch)
        self._on_event(Timed(stopwatch.timing()))

    def _answer(self, text: str, stopwatch: Stopwatch) -> None:
        """Pede a resposta e fala, começando pela primeira frase se a IA a entregar aos poucos."""

        def first_sound() -> None:
            stopwatch.mark("first_sound")
            self._on_event(StateChanged(State.SPEAKING))

        speech = SpeechStream(self._speaker, on_first_sound=first_sound)

        def on_text(piece: str) -> None:
            if piece.strip():
                stopwatch.mark("first_text")
            speech.feed(piece)

        reply = ""
        try:
            reply = self._assistant.reply(text, on_text=on_text if self.stream_speech else None)
            stopwatch.mark("replied")
            self._on_event(Replied(reply))
        finally:
            # Se nada chegou aos poucos (resposta inteira ou mensagem de erro), fala a resposta.
            speech.finish(fallback=reply)
            stopwatch.mark("done")
