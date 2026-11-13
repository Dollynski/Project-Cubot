import hashlib
from pathlib import Path

import httpx2
import pytest

from cubo.config import VoiceSettings
from cubo.voice import models
from cubo.voice.models import (
    DownloadError,
    default_data_dir,
    download_piper_voice,
    download_wake_word,
    download_whisper,
    missing_models,
    piper_voice_path,
    prepare_models,
    wake_word_path,
    whisper_dir,
    whisper_downloaded,
)

CONTENT = b"modelo de teste"


@pytest.fixture
def pinned_model(monkeypatch):
    """Faz o ``hey_jarvis`` de teste ter o SHA-256 do conteúdo falso."""
    monkeypatch.setitem(models.WAKE_WORD_SHA256, "hey_jarvis", hashlib.sha256(CONTENT).hexdigest())


def client(handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


class Server:
    def __init__(self, content=CONTENT, status=200):
        self.requests = []
        self._content = content
        self._status = status

    def __call__(self, request):
        self.requests.append(request)
        return httpx2.Response(self._status, content=self._content)


def test_data_dir_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CUBO_DATA_DIR", str(tmp_path / "dados"))
    assert default_data_dir() == tmp_path / "dados"

    monkeypatch.delenv("CUBO_DATA_DIR")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == tmp_path / "xdg" / "cubo"


def test_paths_are_grouped_by_kind(tmp_path):
    assert wake_word_path("hey_jarvis", tmp_path) == tmp_path / "wakeword" / "hey_jarvis.onnx"
    assert piper_voice_path("pt_BR-faber-medium", tmp_path) == (
        tmp_path / "piper" / "pt_BR-faber-medium.onnx"
    )
    assert whisper_dir(tmp_path) == tmp_path / "whisper"


def test_custom_wake_word_is_a_path_chosen_by_the_user(tmp_path):
    assert wake_word_path("~/meu_modelo.onnx", tmp_path) == Path("~/meu_modelo.onnx").expanduser()


def test_download_saves_the_verified_model(tmp_path, pinned_model):
    server = Server()

    with client(server) as http:
        path = download_wake_word("hey_jarvis", tmp_path, http)

    assert path.read_bytes() == CONTENT
    assert str(server.requests[0].url).endswith("/v2.1.2/hey_jarvis.onnx")
    assert [item.name for item in path.parent.iterdir()] == ["hey_jarvis.onnx"]


def test_download_is_skipped_when_the_file_is_already_good(tmp_path, pinned_model):
    server = Server()
    with client(server) as http:
        download_wake_word("hey_jarvis", tmp_path, http)
        download_wake_word("hey_jarvis", tmp_path, http)

    assert len(server.requests) == 1


def test_corrupted_file_is_downloaded_again(tmp_path, pinned_model):
    target = wake_word_path("hey_jarvis", tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"pela metade")

    with client(Server()) as http:
        download_wake_word("hey_jarvis", tmp_path, http)

    assert target.read_bytes() == CONTENT


def test_download_with_wrong_hash_is_rejected_and_not_saved(tmp_path, pinned_model):
    with (
        client(Server(content=b"adulterado")) as http,
        pytest.raises(DownloadError, match="SHA-256"),
    ):
        download_wake_word("hey_jarvis", tmp_path, http)

    assert not wake_word_path("hey_jarvis", tmp_path).exists()


def test_download_http_error_is_reported(tmp_path, pinned_model):
    with client(Server(status=404)) as http, pytest.raises(DownloadError, match="hey_jarvis"):
        download_wake_word("hey_jarvis", tmp_path, http)


def test_download_network_failure_is_reported(tmp_path, pinned_model):
    def offline(request):
        raise httpx2.ConnectError("sem rede", request=request)

    with client(offline) as http, pytest.raises(DownloadError, match="hey_jarvis"):
        download_wake_word("hey_jarvis", tmp_path, http)


def test_only_known_models_can_be_downloaded(tmp_path):
    with client(Server()) as http, pytest.raises(DownloadError, match="não é um modelo pronto"):
        download_wake_word("outro", tmp_path, http)


def fake_piper_download(monkeypatch, *, error=None):
    calls = []

    def download_voice(voice, directory):
        calls.append(voice)
        if error:
            raise error
        (directory / f"{voice}.onnx").write_bytes(b"onnx")
        (directory / f"{voice}.onnx.json").write_bytes(b"{}")

    monkeypatch.setattr("piper.download_voices.download_voice", download_voice)
    return calls


def test_piper_voice_lands_complete_in_the_data_dir(tmp_path, monkeypatch):
    fake_piper_download(monkeypatch)

    path = download_piper_voice("pt_BR-faber-medium", tmp_path)

    assert path.read_bytes() == b"onnx"
    assert sorted(item.name for item in path.parent.iterdir()) == [
        "pt_BR-faber-medium.onnx",
        "pt_BR-faber-medium.onnx.json",
    ]


def test_piper_voice_is_not_downloaded_twice(tmp_path, monkeypatch):
    calls = fake_piper_download(monkeypatch)

    download_piper_voice("pt_BR-faber-medium", tmp_path)
    download_piper_voice("pt_BR-faber-medium", tmp_path)

    assert calls == ["pt_BR-faber-medium"]


def test_failed_piper_download_leaves_nothing_behind(tmp_path, monkeypatch):
    fake_piper_download(monkeypatch, error=OSError("sem rede"))

    with pytest.raises(DownloadError, match="sem rede"):
        download_piper_voice("pt_BR-faber-medium", tmp_path)

    assert list((tmp_path / "piper").iterdir()) == []


def test_whisper_is_downloaded_into_the_data_dir(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "faster_whisper.download_model", lambda name, cache_dir: calls.append((name, cache_dir))
    )

    download_whisper("base", tmp_path)

    assert calls == [("base", str(tmp_path / "whisper"))]


def test_whisper_failure_is_reported(tmp_path, monkeypatch):
    def offline(name, cache_dir):
        raise OSError("sem rede")

    monkeypatch.setattr("faster_whisper.download_model", offline)

    with pytest.raises(DownloadError, match="base"):
        download_whisper("base", tmp_path)


def test_everything_is_missing_in_an_empty_data_dir(tmp_path):
    missing = missing_models(VoiceSettings(), tmp_path)

    assert len(missing) == 3
    assert "palavra de ativação 'hey_jarvis'" in missing[0]
    assert "voz 'pt_BR-faber-medium'" in missing[1]
    assert "modelo de transcrição 'base' (cerca de 145 MB)" in missing[2]


def test_nothing_is_missing_when_the_files_are_there(tmp_path, monkeypatch):
    settings = VoiceSettings()
    wake = wake_word_path(settings.wake_word, tmp_path)
    voice = piper_voice_path(settings.piper_voice, tmp_path)
    for path in (wake, voice, voice.with_name(f"{voice.name}.json")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    monkeypatch.setattr(models, "whisper_downloaded", lambda *_: True)

    assert missing_models(settings, tmp_path) == []


def test_a_custom_wake_word_is_not_ours_to_download(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "whisper_downloaded", lambda *_: True)
    settings = VoiceSettings(wake_word=str(tmp_path / "meu.onnx"))

    assert all("palavra de ativação" not in item for item in missing_models(settings, tmp_path))


def test_whisper_is_not_downloaded_in_an_empty_data_dir(tmp_path):
    assert whisper_downloaded("base", tmp_path) is False


def test_prepare_downloads_everything_and_reports_progress(tmp_path, monkeypatch):
    done = []
    monkeypatch.setattr(models, "download_wake_word", lambda name, *_: done.append(name))
    monkeypatch.setattr(models, "download_piper_voice", lambda voice, _dir: done.append(voice))
    monkeypatch.setattr(models, "download_whisper", lambda model, _dir: done.append(model))
    messages = []

    prepare_models(VoiceSettings(), tmp_path, messages.append)

    assert done == ["hey_jarvis", "pt_BR-faber-medium", "base"]
    assert len(messages) == 3
