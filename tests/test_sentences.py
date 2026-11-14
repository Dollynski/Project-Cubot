import pytest

from cubo.voice.sentences import SentenceSplitter


def split(chunks):
    splitter = SentenceSplitter()
    sentences = []
    for chunk in chunks:
        sentences += splitter.feed(chunk)
    if rest := splitter.flush():
        sentences.append(rest)
    return sentences


def test_returns_each_sentence_as_soon_as_it_is_complete():
    splitter = SentenceSplitter()

    assert splitter.feed("Olá, tudo") == []
    assert splitter.feed(" bem? Eu sou") == ["Olá, tudo bem?"]
    assert splitter.feed(" o Cubô. Como posso") == ["Eu sou o Cubô."]
    assert splitter.feed(" ajudar?") == ["Como posso ajudar?"]


def test_a_final_period_waits_for_what_comes_next():
    splitter = SentenceSplitter()

    assert splitter.feed("Oi.") == []
    assert splitter.flush() == "Oi."


def test_a_period_followed_by_a_capital_ends_the_sentence():
    splitter = SentenceSplitter()

    assert splitter.feed("Oi. Tudo") == ["Oi."]


def test_a_period_inside_a_number_does_not_end_the_sentence():
    assert split(["A temperatura é 3", ".5 graus. Mais frio amanhã."]) == [
        "A temperatura é 3.5 graus.",
        "Mais frio amanhã.",
    ]


def test_a_period_before_a_lowercase_word_does_not_end_the_sentence():
    assert split(["Tem pão, leite etc. e tal. Vou ao mercado."]) == [
        "Tem pão, leite etc. e tal.",
        "Vou ao mercado.",
    ]


def test_titles_do_not_end_the_sentence():
    assert split(["O Dr. Silva chegou. A Sra. Lima saiu."]) == [
        "O Dr. Silva chegou.",
        "A Sra. Lima saiu.",
    ]


def test_line_breaks_end_the_sentence_at_once():
    splitter = SentenceSplitter()

    assert splitter.feed("- primeiro item\n- segundo") == ["- primeiro item"]
    assert splitter.flush() == "- segundo"


def test_question_and_exclamation_marks_end_the_sentence_at_once():
    splitter = SentenceSplitter()

    assert splitter.feed("Sério?! Que") == ["Sério?!"]
    assert splitter.feed(" legal!") == ["Que legal!"]


def test_closing_quotes_stay_with_their_sentence():
    assert split(['Ele disse "vamos!" Depois saiu.']) == ['Ele disse "vamos!"', "Depois saiu."]


def test_markdown_marks_stay_with_their_sentence():
    assert split(["**Pronto!** Liguei a luz. _Mais_ algo."]) == [
        "**Pronto!**",
        "Liguei a luz.",
        "_Mais_ algo.",
    ]


def test_pieces_without_words_are_dropped():
    assert split(["...", " ", "Oi!", " ... "]) == ["Oi!"]


def test_a_long_text_without_punctuation_is_cut_at_a_comma():
    text = "uma frase muito longa, " * 12 + "que continua sem parar"

    sentences = split([text])

    assert len(sentences) > 1
    assert all(len(sentence) <= 210 for sentence in sentences)
    assert " ".join(sentences).replace("  ", " ") == text


def test_the_unfinished_end_comes_out_on_flush():
    assert split(["Primeira frase. Segunda sem ponto"]) == ["Primeira frase.", "Segunda sem ponto"]


@pytest.mark.parametrize("size", [1, 2, 3, 5, 8])
def test_the_result_does_not_depend_on_how_the_text_is_chunked(size):
    text = (
        "Olá! Hoje está 25.5 graus, o Dr. Silva disse que sim... Tudo bem? "
        "Claro.\n- item um\n- item dois. Fim."
    )
    chunks = [text[start : start + size] for start in range(0, len(text), size)]

    assert split(chunks) == split([text])
