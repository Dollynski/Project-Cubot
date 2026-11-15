"""O Cubô não cai com traceback quando um modelo de voz está corrompido."""

import cubo.__main__ as cli
from tests.test_cli import configure_gemini_key


def test_a_corrupted_wake_word_stops_the_voice_with_a_message_not_a_traceback(capsys):
    from cubo.voice.models import default_data_dir, wake_word_path

    configure_gemini_key()
    path = wake_word_path("hey_jarvis", default_data_dir())
    path.parent.mkdir(parents=True)
    path.write_bytes(b"cortado no meio")

    assert cli.main(["--sem-painel"]) == 2

    error = capsys.readouterr().err
    assert "corrompido ou incompleto" in error
    assert "cubo preparar" in error
