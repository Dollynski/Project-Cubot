"""Fala o texto à medida que ele chega, uma frase por vez, sem esperar a resposta terminar."""

import logging
import queue
import threading
from collections.abc import Callable

from cubo.speech_text import to_speech
from cubo.voice.audio import AudioClip
from cubo.voice.sentences import SentenceSplitter
from cubo.voice.tts import Speaker, SynthesisError

logger = logging.getLogger(__name__)

# Quantas frases já sintetizadas podem esperar a vez de tocar.
READY_CLIPS = 3


class SpeechStream:
    """Transforma o texto que chega aos poucos em fala, em duas etapas encadeadas.

    Uma thread sintetiza a frase seguinte enquanto a outra toca a atual, então o Cubô começa a
    falar assim que a primeira frase está pronta e não tem pausas entre as frases.
    """

    def __init__(
        self, speaker: Speaker, *, on_first_sound: Callable[[], None] = lambda: None
    ) -> None:
        self._speaker = speaker
        self._on_first_sound = on_first_sound
        self._splitter = SentenceSplitter()
        self._sentences: queue.Queue[str | None] = queue.Queue()
        self._clips: queue.Queue[AudioClip | None] = queue.Queue(maxsize=READY_CLIPS)
        self._queued_any = False
        self._workers = [
            threading.Thread(target=self._synthesize, name="cubo-sintese", daemon=True),
            threading.Thread(target=self._play, name="cubo-fala", daemon=True),
        ]
        for worker in self._workers:
            worker.start()

    def feed(self, text: str) -> None:
        """Recebe mais um pedaço do texto da resposta."""
        for sentence in self._splitter.feed(text):
            self._queue(sentence)

    def finish(self, fallback: str = "") -> None:
        """Fala o que faltava e espera terminar de falar.

        Se nada chegou aos poucos (a resposta veio inteira, ou foi uma mensagem de erro), fala o
        ``fallback``.
        """
        if rest := self._splitter.flush():
            self._queue(rest)
        if not self._queued_any and fallback:
            self._queue(fallback)
        self._sentences.put(None)
        for worker in self._workers:
            worker.join()

    def _queue(self, sentence: str) -> None:
        self._queued_any = True
        self._sentences.put(sentence)

    def _synthesize(self) -> None:
        try:
            while (sentence := self._sentences.get()) is not None:
                if not (spoken := to_speech(sentence)):
                    continue
                try:
                    self._clips.put(self._speaker.synthesize(spoken))
                except SynthesisError:
                    logger.exception("Falha ao sintetizar a frase")
        finally:
            self._clips.put(None)

    def _play(self) -> None:
        first = True
        while (clip := self._clips.get()) is not None:
            try:
                if first:
                    first = False
                    self._on_first_sound()
                self._speaker.play(clip)
            except Exception:
                # Falhar numa frase (alto-falante, por exemplo) não impede as próximas.
                logger.exception("Falha ao tocar a frase")
