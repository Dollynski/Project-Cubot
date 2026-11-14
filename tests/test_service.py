import pytest

from cubo.activity import ActivityLog
from cubo.config import Config, Device, VoiceSettings, load_config
from cubo.credentials import CredentialStore
from cubo.errors import SetupError
from cubo.service import AI_UNAVAILABLE_SPEECH, CuboService
from cubo.usage import UsageTracker
from cubo.voice.events import Heard
from tests.fakes import FakeRuntimeFactory, FakeVoiceFactory


@pytest.fixture
def parts():
    return FakeRuntimeFactory(), FakeVoiceFactory()


def make_service(tmp_path, parts, listener=None, voice=True):
    runtime_factory, voice_factory = parts
    return CuboService(
        config=Config(),
        config_path=tmp_path / "config.toml",
        credentials=CredentialStore(tmp_path / "secrets.toml", environ={}),
        data_dir=tmp_path,
        usage=UsageTracker(),
        voice_factory=voice_factory if voice else None,
        activity=ActivityLog(),
        on_event=listener,
        runtime_factory=runtime_factory,
    )


def with_speed(speed):
    config = Config()
    config.voice = VoiceSettings(speech_speed=speed)
    return config


def with_model(model):
    config = Config()
    config.llm.provider = "ollama"
    config.llm.models.ollama = model
    return config


def test_start_brings_up_the_ai_and_the_voice(tmp_path, parts):
    service = make_service(tmp_path, parts)

    service.start()

    assert service.problems == {}
    assert service.voice.started
    assert service.voice.assistant == "assistente 1"
    assert service.warnings == ["aviso 1", "aviso de voz"]


def test_without_ai_the_voice_still_runs_and_explains(tmp_path, parts):
    runtime_factory, _ = parts
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")
    service = make_service(tmp_path, parts)

    service.start()

    assert service.problems == {"ia": "Nenhuma chave de API configurada para Gemini."}
    assert service.voice.assistant.reply("oi") == AI_UNAVAILABLE_SPEECH


def test_a_voice_failure_does_not_stop_the_ai(tmp_path, parts):
    _, voice_factory = parts
    voice_factory.fail_with = SetupError("Modelo de wake word não encontrado.")
    service = make_service(tmp_path, parts)

    service.start()

    assert service.problems == {"voz": "Modelo de wake word não encontrado."}
    assert service.voice is None
    assert service.runtime is not None


def test_without_a_voice_factory_only_the_ai_runs(tmp_path, parts):
    service = make_service(tmp_path, parts, voice=False)

    service.start()

    assert service.voice is None
    assert service.problems == {}


def test_voice_changes_do_not_rebuild_the_assistant(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()

    reloaded = service.apply(with_speed(1.5))

    assert reloaded == ["voz"]
    assert len(runtime_factory.runtimes) == 1
    assert service.voice.reconfigured == [VoiceSettings(speech_speed=1.5)]
    assert load_config(tmp_path / "config.toml").voice.speech_speed == 1.5
    assert service.config.voice.speech_speed == 1.5


def test_ai_changes_replace_the_assistant_and_close_the_old_one(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()

    reloaded = service.apply(with_model("llama3"))

    first, second = runtime_factory.runtimes
    assert reloaded == ["IA e Home Assistant"]
    assert first.closed and not second.closed
    assert service.voice.assistant == "assistente 2"
    assert service.voice.reconfigured == [VoiceSettings()]


def test_a_config_that_does_not_load_is_neither_applied_nor_saved(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Claude.")

    with pytest.raises(SetupError, match="Claude"):
        service.apply(with_model("llama3"))

    assert service.config == Config()
    assert not (tmp_path / "config.toml").exists()
    assert not runtime_factory.runtimes[0].closed
    assert service.voice.assistant == "assistente 1"


def test_a_voice_that_does_not_load_discards_the_new_assistant(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()
    service.voice.reconfigure_error = SetupError("Modelo de transcrição não baixado.")
    config = with_model("llama3")
    config.voice = VoiceSettings(whisper_model="small")

    with pytest.raises(SetupError, match="transcrição"):
        service.apply(config)

    assert service.config == Config()
    assert not (tmp_path / "config.toml").exists()
    new_runtime = runtime_factory.runtimes[1]
    assert new_runtime.closed
    assert not runtime_factory.runtimes[0].closed


def test_saving_something_else_is_not_blocked_by_an_ai_that_was_already_down(tmp_path, parts):
    runtime_factory, _ = parts
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")
    service = make_service(tmp_path, parts)
    service.start()

    reloaded = service.apply(with_speed(1.5))

    assert reloaded == ["voz"]
    assert "ia" in service.problems
    assert load_config(tmp_path / "config.toml").voice.speech_speed == 1.5


def test_saving_retries_a_voice_that_was_down(tmp_path, parts):
    _, voice_factory = parts
    voice_factory.fail_with = SetupError("Dispositivo inválido.")
    service = make_service(tmp_path, parts)
    service.start()
    voice_factory.fail_with = None

    service.apply(with_speed(1.5))

    assert service.voice.started
    assert "voz" not in service.problems


def test_saving_a_key_reloads_the_assistant(tmp_path, parts):
    runtime_factory, _ = parts
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")
    service = make_service(tmp_path, parts)
    service.start()
    runtime_factory.fail_with = None

    service.save_credential("gemini", "AIza-nova-1234")

    assert service.credentials.get("gemini") == "AIza-nova-1234"
    assert "ia" not in service.problems
    assert service.voice.assistant == "assistente 1"


def test_deleting_a_key_takes_the_ai_down_and_keeps_the_voice(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.credentials.set("gemini", "AIza-velha-1234")
    service.start()
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")

    service.delete_credential("gemini")

    assert service.credentials.get("gemini") is None
    assert service.runtime is None
    assert service.voice.assistant.reply("oi") == AI_UNAVAILABLE_SPEECH
    assert runtime_factory.runtimes[0].closed


def test_restart_voice_builds_a_new_session(tmp_path, parts):
    _, voice_factory = parts
    service = make_service(tmp_path, parts)
    service.start()

    service.restart_voice()

    first, second = voice_factory.sessions
    assert first.stopped and second.started
    assert service.voice is second


def test_stop_stops_everything(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()

    service.stop()

    assert service.voice.stopped
    assert runtime_factory.runtimes[0].closed


def test_events_go_to_the_activity_log_and_to_the_listener(tmp_path, parts):
    heard = []
    service = make_service(tmp_path, parts, listener=heard.append)
    service.start()

    service.voice.on_event(Heard("oi"))

    assert [entry.text for entry in service.activity.entries()] == ["oi"]
    assert heard == [Heard("oi")]


def test_the_call_limits_follow_the_config_even_without_an_ai(tmp_path, parts):
    runtime_factory, _ = parts
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")
    service = make_service(tmp_path, parts)

    service.start()
    assert service.usage.snapshot().max_calls_per_minute == 20

    config = Config()
    config.llm.max_calls_per_minute = 5
    config.llm.max_calls_per_day = 100
    reloaded = service.apply(config)

    snapshot = service.usage.snapshot()
    assert (snapshot.max_calls_per_minute, snapshot.max_calls_per_day) == (5, 100)
    assert reloaded == ["limites de chamadas"]


def test_changing_only_the_limits_does_not_rebuild_the_assistant(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()
    config = Config()
    config.llm.max_calls_per_day = 100

    service.apply(config)

    assert len(runtime_factory.runtimes) == 1
    assert not runtime_factory.runtimes[0].closed


def test_devices_can_be_saved_while_the_ai_is_still_down(tmp_path, parts):
    runtime_factory, _ = parts
    runtime_factory.fail_with = SetupError("Nenhuma chave de API configurada para Gemini.")
    service = make_service(tmp_path, parts)
    service.start()
    config = Config()
    config.home_assistant.devices = [Device(entity_id="light.sala", alias="luz da sala")]

    service.apply(config)

    assert (
        load_config(tmp_path / "config.toml").home_assistant.devices
        == config.home_assistant.devices
    )
    assert "ia" in service.problems


def test_devices_changes_rebuild_the_assistant_that_lists_them(tmp_path, parts):
    runtime_factory, _ = parts
    service = make_service(tmp_path, parts)
    service.start()
    config = Config()
    config.home_assistant.devices = [Device(entity_id="light.sala", alias="luz da sala")]

    reloaded = service.apply(config)

    assert reloaded == ["IA e Home Assistant"]
    assert len(runtime_factory.runtimes) == 2
    assert service.voice.assistant == "assistente 2"
