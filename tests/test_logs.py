import io
import logging

import pytest

from cubo.logs import MASK, configure_logging, redact


@pytest.fixture
def captured_log():
    stream = io.StringIO()
    configure_logging(lambda: ["segredo-cadastrado-123"], stream=stream)
    yield stream
    logging.getLogger().handlers.clear()


def test_redacts_known_secret_in_message_and_arguments(captured_log):
    logging.getLogger("teste").warning("chave %s", "segredo-cadastrado-123")

    assert "segredo-cadastrado-123" not in captured_log.getvalue()
    assert MASK in captured_log.getvalue()


def test_redacts_secret_inside_traceback(captured_log):
    try:
        raise RuntimeError("falhou com segredo-cadastrado-123")
    except RuntimeError:
        logging.getLogger("teste").exception("erro")

    output = captured_log.getvalue()
    assert "Traceback" in output
    assert "segredo-cadastrado-123" not in output


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
        "AIzaSyA1234567890abcdefghijklmnop",
        "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJoYSJ9.c2lnbmF0dXJh",
    ],
)
def test_redacts_key_shaped_text_not_registered(secret):
    assert redact(f"erro: {secret}", secrets=[]) == f"erro: {MASK}"


def test_ignores_secrets_too_short_to_redact_safely():
    assert redact("ligar a luz", secrets=["a"]) == "ligar a luz"
