"""Divide o texto que chega aos poucos em frases, para começar a falar sem esperar o fim."""

# Títulos que levam ponto sem terminar a frase ("Dr. Silva").
ABBREVIATIONS = frozenset({"sr", "sra", "srta", "dr", "dra", "prof", "profa", "av", "ex", "exa"})

# O que pode vir colado depois da pontuação e ainda pertence à mesma frase: mais pontuação,
# aspas, parênteses e os marcadores de negrito, itálico e código do Markdown.
CLOSERS = "!?….\"')”*_`"

# Sem pontuação por muito tempo, a frase é cortada numa vírgula para a fala não demorar.
MAX_UNBROKEN_CHARS = 200
SOFT_BREAKS = (", ", "; ", ": ")


class SentenceSplitter:
    """Recebe pedaços de texto e devolve cada frase assim que ela se completa.

    O ponto final só vale depois de ver o que vem em seguida: "3.5" e "Dr. Silva" não terminam
    a frase. Já "?", "!", "…" e a quebra de linha terminam na hora.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        sentences = []
        while (end := _find_end(self._buffer)) is not None:
            sentence, self._buffer = self._buffer[:end].strip(), self._buffer[end:]
            if _has_words(sentence):
                sentences.append(sentence)
        return sentences

    def flush(self) -> str | None:
        """O que sobrou quando o texto acabou, mesmo sem pontuação final."""
        rest, self._buffer = self._buffer.strip(), ""
        return rest if _has_words(rest) else None


def _has_words(text: str) -> bool:
    return any(char.isalnum() for char in text)


def _find_end(text: str) -> int | None:
    """Posição logo depois do fim da primeira frase completa, ou ``None`` se ainda não há."""
    for index, char in enumerate(text):
        if char == "\n":
            return index + 1
        if char in "!?…":
            return _after_run(text, index)
        if char == "." and (end := _period_end(text, index)) is not None:
            return end
    if len(text) > MAX_UNBROKEN_CHARS:
        return _soft_break(text)
    return None


def _after_run(text: str, index: int) -> int:
    """Pula pontuação repetida ("?!", "...") e aspas ou parênteses que fecham a frase."""
    while index + 1 < len(text) and text[index + 1] in CLOSERS:
        index += 1
    return index + 1


def _period_end(text: str, index: int) -> int | None:
    end = _after_run(text, index)
    if end >= len(text):
        return None  # ainda não dá para saber se a frase terminou
    if not text[end].isspace():
        return None  # "3.5", "site.com"
    rest = text[end:].lstrip()
    if not rest:
        return None
    if rest[0].islower():
        return None  # "etc. e tal": a frase continua
    if _word_before(text, index).lower() in ABBREVIATIONS:
        return None
    return end


def _word_before(text: str, index: int) -> str:
    start = index
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    return text[start:index]


def _soft_break(text: str) -> int | None:
    cut = max((text.rfind(mark, 0, MAX_UNBROKEN_CHARS) for mark in SOFT_BREAKS), default=-1)
    return cut + 1 if cut > 0 else None
