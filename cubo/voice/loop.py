"""O ciclo de voz: espera a wake word, escuta o pedido, responde falando."""

import logging
import threading
from collections.abc import Callable, Iterator
from typing import Protocol

import numpy as np

from cubo.assistant import Assistant
from cubo.voice.events import Event, Heard, Replied, State, StateChanged
from cubo.voice.listening import UtteranceRecorder
from cubo.voice.stt import Transcriber
from cubo.voice.tts import Speaker
from cubo.voice.wake_word import WakeWordDetector

logger = logging.getLogger(__name__)


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
        assistant: Assistant,
        speaker: Speaker,
        on_event: Callable[[Event], None] = lambda _event: None,
    ) -> None:
        self._microphone = microphone
        self._wake_word = wake_word
        self._recorder = recorder
        self._transcriber = transcriber
        self._assistant = assistant
        self._speaker = speaker
        self._on_event = on_event

    def run(self, stop: threading.Event) -> None:
        """Atende pedidos até ``stop`` ser acionado."""
        frames = self._microphone.frames(stop)
        self._on_event(StateChanged(State.WAITING))
        for frame in frames:
            if self._wake_word.detected(frame):
                self._attend(frames)
                self._on_event(StateChanged(State.WAITING))

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

        self._on_event(StateChanged(State.TRANSCRIBING))
        text = self._transcriber.transcribe(audio)
        if not text:
            return
        self._on_event(Heard(text))

        self._on_event(StateChanged(State.THINKING))
        reply = self._assistant.reply(text)
        self._on_event(Replied(reply))

        self._on_event(StateChanged(State.SPEAKING))
        self._speaker.say(reply)
