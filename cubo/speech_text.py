"""Prepara o texto da IA para ser falado: tira markdown, links e emojis."""

import re

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_INLINE_CODE = re.compile(r"`([^`]*)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|~~)(?=\S)(.+?)(?<=\S)\1")
_EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emojis, símbolos e pictogramas
    "\U00002190-\U000021ff"  # setas
    "\U00002600-\U000027bf"  # símbolos diversos e dingbats
    "\U00002b00-\U00002bff"  # estrelas e setas extras
    "️‍"  # seletor de variação e junção de emojis
    "]"
)
_SPACES = re.compile(r"[ \t]+")
_SENTENCE_END = (".", "!", "?", ":", ";", ",")


def to_speech(text: str) -> str:
    """Converte a resposta em texto corrido, numa linha só, pronto para o sintetizador."""
    text = _CODE_BLOCK.sub(" ", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _LIST_MARKER.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _EMOJI.sub("", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return " ".join(_end_sentence(line) for line in lines if line)


def _end_sentence(line: str) -> str:
    """Itens de lista viram frases, para o sintetizador fazer a pausa entre eles."""
    return line if line.endswith(_SENTENCE_END) else f"{line}."
