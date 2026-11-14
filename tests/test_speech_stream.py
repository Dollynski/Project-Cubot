import threading

import numpy as np
import pytest

from cubo.voice.audio import AudioClip
from cubo.voice.speech_stream import SpeechStream
from cubo.voice.tts import SynthesisError


class FakeSpeaker:
    """Anota a ordem de tudo e deixa o teste controlar quando a fala termina."""

    def __init__(self):
        self.events = []
        self.fail_on = set()
        self.play_error = None
        self.second_synthesis = threading.Event()
        self.hold_first_play = False

    def synthesize(self, text):
        self.events.append(("síntese", text))
        if text in self.fail_on:
            raise SynthesisError("sem voz")
        if len([e for e in self.events if e[0] == "síntese"]) == 2:
            self.second_synthesis.set()
        return AudioClip(np.array([0.1], np.float32), 22_050)

    def play(self, clip):
        self.events.append(("toca", len(clip.samples)))
        if self.hold_first_play:
            self.hold_first_play = False
            # A primeira frase "toca" até a segunda estar sintetizada: prova que há encadeamento.
            assert self.second_synthesis.wait(2.0)
        if self.play_error:
            raise self.play_error


def spoken(speaker):
    return [text for kind, text in speaker.events if kind == "síntese"]


def test_speaks_each_sentence_in_order():
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.feed("Olá, tudo bem? Eu sou")
    stream.feed(" o Cubô. Posso ajudar")
    stream.finish()

    # O texto limpo ganha o ponto final que faltava, como em qualquer resposta falada.
    assert spoken(speaker) == ["Olá, tudo bem?", "Eu sou o Cubô.", "Posso ajudar."]
    assert [kind for kind, _ in speaker.events].count("toca") == 3


def test_the_next_sentence_is_synthesized_while_the_current_one_plays():
    speaker = FakeSpeaker()
    speaker.hold_first_play = True
    stream = SpeechStream(speaker)

    stream.feed("Primeira frase. Segunda frase. Terceira frase.")
    stream.finish()

    assert speaker.second_synthesis.is_set()
    assert spoken(speaker) == ["Primeira frase.", "Segunda frase.", "Terceira frase."]


def test_markdown_and_emoji_are_cleaned_before_speaking():
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.feed("**Pronto!** Liguei a luz 💡\n")
    stream.finish()

    assert spoken(speaker) == ["Pronto!", "Liguei a luz."]


def test_the_first_sound_is_announced_once_and_before_it_plays():
    speaker = FakeSpeaker()
    announced = []
    stream = SpeechStream(speaker, on_first_sound=lambda: announced.append(len(speaker.events)))

    stream.feed("Um. Dois. Três.")
    stream.finish()

    assert len(announced) == 1
    # No momento do aviso, só a primeira síntese tinha acontecido (nada tocou ainda).
    assert ("toca", 1) not in speaker.events[: announced[0]]


def test_the_fallback_is_spoken_when_nothing_arrived_in_pieces():
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.finish(fallback="Atingi o limite de chamadas.")

    assert spoken(speaker) == ["Atingi o limite de chamadas."]


def test_the_fallback_is_ignored_when_the_text_was_already_spoken():
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.feed("Já falei isso.")
    stream.finish(fallback="Resposta inteira repetida.")

    assert spoken(speaker) == ["Já falei isso."]


def test_without_any_text_nothing_is_spoken_and_it_still_finishes():
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.finish()

    assert speaker.events == []


def test_a_sentence_that_fails_to_synthesize_does_not_stop_the_others():
    speaker = FakeSpeaker()
    speaker.fail_on = {"Segunda."}
    stream = SpeechStream(speaker)

    stream.feed("Primeira. Segunda. Terceira.")
    stream.finish()

    plays = [event for event in speaker.events if event[0] == "toca"]
    assert len(plays) == 2


def test_a_sentence_that_fails_to_play_does_not_stop_the_others():
    speaker = FakeSpeaker()
    speaker.play_error = RuntimeError("alto-falante sumiu")
    stream = SpeechStream(speaker)

    stream.feed("Primeira. Segunda.")
    stream.finish()

    assert [kind for kind, _ in speaker.events].count("toca") == 2


@pytest.mark.parametrize("piece", ["", "   ", "💡"])
def test_pieces_without_words_are_not_spoken(piece):
    speaker = FakeSpeaker()
    stream = SpeechStream(speaker)

    stream.feed(piece)
    stream.finish()

    assert spoken(speaker) == []
