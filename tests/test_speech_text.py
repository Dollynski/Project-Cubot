from cubo.speech_text import to_speech


def test_keeps_plain_portuguese_text():
    assert to_speech("A luz da sala está ligada.") == "A luz da sala está ligada."


def test_removes_markdown_emphasis_and_headings():
    assert to_speech("## Pronto\n**Liguei** a _luz_ da ~~cozinha~~ sala.") == (
        "Pronto. Liguei a luz da cozinha sala."
    )


def test_turns_list_items_into_sentences():
    assert to_speech("Posso:\n- ligar a luz\n- ler a temperatura\n1. cantar") == (
        "Posso: ligar a luz. ler a temperatura. cantar."
    )


def test_keeps_link_text_and_drops_urls():
    text = "Veja [a previsão](https://tempo.example) ou https://outro.example agora."
    assert to_speech(text) == "Veja a previsão ou agora."


def test_drops_emojis_and_code_blocks():
    assert to_speech("Feito! 💡✅\n```python\nprint(1)\n```") == "Feito!"


def test_keeps_inline_code_text_and_math():
    assert to_speech("Use `ligar` e conte 2 * 3 * 4.") == "Use ligar e conte 2 * 3 * 4."
