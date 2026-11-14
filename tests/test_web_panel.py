import json
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from nicegui import ui
from nicegui.storage import Storage
from nicegui.testing import user_simulation

from cubo.activity import ActivityLog
from cubo.config import Config, Device, VoiceSettings
from cubo.credentials import CredentialStore
from cubo.errors import SetupError
from cubo.llm.base import ProviderError
from cubo.service import CuboService
from cubo.tools.home_assistant import HomeAssistantError
from cubo.usage import UsageTracker
from cubo.voice.events import Heard, Replied, Timed
from cubo.voice.timing import Timing
from cubo.web.auth import LoginThrottle, PanelAuth
from cubo.web.pages import ai as ai_page
from cubo.web.pages import audio as audio_page
from cubo.web.pages import home_assistant as house_page
from cubo.web.pages import voice as voice_page
from cubo.web.panel import Panel
from tests.fakes import FakeRuntimeFactory, FakeVoiceFactory
from tests.web_support import current

pytestmark = pytest.mark.anyio

MAIN_FILE = Path(__file__).parent / "web_app_main.py"
PASSWORD = "senha-de-teste-123"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Painel de verdade, com o serviço usando IA e voz falsas."""
    monkeypatch.setattr(Storage, "path", tmp_path / "nicegui")
    runtime_factory, voice_factory = FakeRuntimeFactory(), FakeVoiceFactory()
    service = CuboService(
        config=Config(),
        config_path=tmp_path / "config.toml",
        credentials=CredentialStore(tmp_path / "secrets.toml", environ={}),
        data_dir=tmp_path / "data",
        usage=UsageTracker(),
        voice_factory=voice_factory,
        activity=ActivityLog(),
        runtime_factory=runtime_factory,
    )
    service.start()
    auth = PanelAuth(tmp_path / "panel.toml")
    panel = Panel(service, auth, LoginThrottle(max_attempts=3, lock_seconds=60))
    current.panel = panel
    yield SimpleNamespace(
        panel=panel,
        service=service,
        auth=auth,
        runtime_factory=runtime_factory,
        voice_factory=voice_factory,
        tmp_path=tmp_path,
    )
    service.stop()


async def notified(user, text, timeout=3.0):
    """Espera uma notificação aparecer: os botões rodam o trabalho em segundo plano."""
    waited = 0.0
    while waited < timeout:
        if user.notify.contains(text):
            return True
        await anyio.sleep(0.05)
        waited += 0.05
    return False


def element(user, kind, label):
    """Elemento de um tipo (select, número...) pelo rótulo, para mudar o valor direto."""
    return next(iter(user.find(kind=kind, content=label).elements))


async def sign_in(user, world):
    world.auth.set_password(PASSWORD)
    await user.open("/entrar")
    user.find("Senha").type(PASSWORD)
    user.find(kind=ui.button, content="Entrar").click()
    await user.should_see("Estado")


async def test_without_a_password_the_panel_asks_for_the_first_access(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/")

        await user.should_see("Primeiro acesso")


async def test_first_access_needs_the_terminal_code(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/primeiro-acesso")
        user.find("Código do terminal").type("errado")
        user.find("Nova senha").type(PASSWORD)
        user.find("Repita a senha").type(PASSWORD)
        user.find("Definir senha").click()

        assert await notified(user, "Código incorreto")
        assert not world.auth.has_password


async def test_first_access_sets_the_password_and_signs_in(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/primeiro-acesso")
        user.find("Código do terminal").type(world.auth.setup_code)
        user.find("Nova senha").type(PASSWORD)
        user.find("Repita a senha").type(PASSWORD)
        user.find("Definir senha").click()

        await user.should_see("Estado")
        assert world.auth.verify(PASSWORD)


async def test_first_access_rejects_passwords_that_do_not_match(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/primeiro-acesso")
        user.find("Código do terminal").type(world.auth.setup_code)
        user.find("Nova senha").type(PASSWORD)
        user.find("Repita a senha").type("outra-senha-123")
        user.find("Definir senha").click()

        assert await notified(user, "não são iguais")
        assert not world.auth.has_password


async def test_with_a_password_the_panel_asks_for_the_login(world):
    world.auth.set_password(PASSWORD)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/ia")

        await user.should_see("Entrar no Cubô")


async def test_a_wrong_password_is_refused(world):
    world.auth.set_password(PASSWORD)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/entrar")
        user.find("Senha").type("senha-errada-123")
        user.find(kind=ui.button, content="Entrar").click()

        assert await notified(user, "Senha incorreta")
        await user.should_not_see("Estado")


async def test_too_many_wrong_passwords_lock_the_login_even_for_the_right_one(world):
    world.auth.set_password(PASSWORD)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await user.open("/entrar")
        for _ in range(3):
            user.find("Senha").type("senha-errada-123")
            user.find(kind=ui.button, content="Entrar").click()
            await anyio.sleep(0.3)
        user.find("Senha").clear().type(PASSWORD)
        user.find(kind=ui.button, content="Entrar").click()

        assert await notified(user, "Muitas tentativas")
        await user.should_not_see("Estado")


async def test_the_right_password_opens_the_panel(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)

        await user.should_see("Conversa recente")


async def test_every_page_needs_the_login(world):
    world.auth.set_password(PASSWORD)
    async with user_simulation(main_file=MAIN_FILE) as user:
        for path in ("/", "/audio", "/voz", "/ia", "/casa", "/seguranca"):
            await user.open(path)
            await user.should_see("Entrar no Cubô")


async def test_home_shows_problems_conversation_and_usage(world):
    world.service.problems["ia"] = "Nenhuma chave de API configurada para Gemini."
    world.service.activity.record(Heard("liga a luz"))
    world.service.activity.record(Replied("Pronto."))
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)

        await user.should_see("Nenhuma chave de API configurada para Gemini.")
        await user.should_see("liga a luz")
        await user.should_see("Pronto.")
        await user.should_see("Chamadas à IA")


async def test_home_can_turn_the_voice_back_on(world):
    world.voice_factory.fail_with = SetupError("Dispositivo inválido.")
    world.service.restart_voice()
    world.voice_factory.fail_with = None
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.should_see("A voz está desligada.")
        user.find("Ligar a voz").click()

        await user.should_see("aguardando")
        assert world.service.voice is not None


async def test_signing_out_returns_to_the_login(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        user.find(marker="sair").click()

        await user.should_see("Entrar no Cubô")
        await user.open("/ia")
        await user.should_see("Entrar no Cubô")


async def test_home_says_there_are_no_measured_requests_yet(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)

        await user.should_see("Tempo de resposta")
        await user.should_see("Ainda não há pedidos medidos.")


async def test_home_shows_the_latency_of_each_stage(world):
    world.service.activity.record(Timed(Timing(0.6, 0.9, 2.0, 1.8, 4.2)))
    world.service.activity.record(Timed(Timing(0.8, None, 3.0, 2.2, 5.0)))
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        client = await user.open("/")

        page = json.dumps(
            [item._to_dict() for item in client.elements.values()], default=str, ensure_ascii=False
        )
        assert "O Cubô começa a falar" in page
        assert "2,2 s" in page  # último pedido
        assert "2,0 s" in page  # média de começar a falar (1,8 e 2,2)
        assert "Média dos últimos 2" in page
        assert "—" in page  # a IA do segundo pedido não entregou aos poucos


# ---- IA

KEY = "AIza-segredo-completo-9876"


def key_field(user):
    return user.find("Chave de API do Gemini")


def save_key_button(user):
    return user.find(kind=ui.button, content="Validar e salvar a chave")


async def test_the_saved_key_is_never_sent_to_the_browser(world):
    world.service.credentials.set("gemini", KEY)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        client = await user.open("/ia")

        page = json.dumps(
            [item._to_dict() for item in client.elements.values()], default=str, ensure_ascii=False
        )
        assert KEY not in page
        assert "••••9876" in page


async def test_an_invalid_key_is_refused_and_not_saved(world, monkeypatch):
    def refuse(*_args, **_options):
        raise ProviderError.invalid_key("Gemini")

    monkeypatch.setattr(ai_page, "list_provider_models", refuse)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/ia")
        key_field(user).type(KEY)
        save_key_button(user).click()

        assert await notified(user, "recusou a chave")
        assert world.service.credentials.get("gemini") is None


async def test_a_valid_key_is_saved_and_the_ai_reloads(world, monkeypatch):
    checked = []
    monkeypatch.setattr(
        ai_page,
        "list_provider_models",
        lambda name, **options: checked.append((name, options["api_key"])) or ["b", "a"],
    )
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/ia")
        key_field(user).type(KEY)
        save_key_button(user).click()

        assert await notified(user, "Chave válida e salva")
        assert checked == [("gemini", KEY)]
        assert world.service.credentials.get("gemini") == KEY
        assert len(world.runtime_factory.runtimes) == 2


async def test_ai_settings_are_saved_and_applied(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/ia")
        element(user, ui.select, "Provedor").set_value("ollama")
        await user.should_see("Endereço do Ollama")
        model = element(user, ui.select, "Modelo")
        model.set_options(["llama3"], value="llama3")
        element(user, ui.number, "Chamadas por dia").set_value(7)
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        llm = world.service.config.llm
        assert (llm.provider, llm.model, llm.max_calls_per_day) == ("ollama", "llama3", 7)
        assert world.service.usage.snapshot().max_calls_per_day == 7


async def test_ai_without_a_chosen_model_is_refused_and_not_saved(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/ia")
        element(user, ui.select, "Provedor").set_value("ollama")
        await user.should_see("Endereço do Ollama")
        world.runtime_factory.fail_with = SetupError("Nenhum modelo escolhido para Ollama.")
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Nenhum modelo escolhido")
        assert world.service.config.llm.provider == "gemini"


# ---- Casa


async def test_a_device_is_added_and_saved(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        user.find("Nome falado").type("luz da sala")
        user.find("ID da entidade").type("light.sala")
        user.find(kind=ui.button, content="Adicionar").click()
        await user.should_see("light.sala")
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        devices = world.service.config.home_assistant.devices
        assert [(d.alias, d.entity_id) for d in devices] == [("luz da sala", "light.sala")]


async def test_an_invalid_entity_id_is_refused(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        user.find("Nome falado").type("luz")
        user.find("ID da entidade").type("Luz da Sala")
        user.find(kind=ui.button, content="Adicionar").click()

        assert await notified(user, "entity_id")
        await user.should_see("Nenhum dispositivo cadastrado.")


async def test_a_device_can_be_removed(world):
    config = Config()
    config.home_assistant.devices = [Device(entity_id="light.sala", alias="luz da sala")]
    world.service.apply(config)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        await user.should_see("light.sala")
        user.find(kind=ui.button, content="delete").click()
        await user.should_see("Nenhum dispositivo cadastrado.")
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        assert world.service.config.home_assistant.devices == []


async def test_the_home_assistant_token_is_checked_before_it_is_saved(world, monkeypatch):
    def refuse(url, token):
        raise HomeAssistantError("O Home Assistant recusou o token (inválido ou expirado).")

    monkeypatch.setattr(house_page, "verify_connection", refuse)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        user.find("Token de acesso").type("token-ruim-0000")
        user.find(kind=ui.button, content="Validar e salvar o token").click()

        assert await notified(user, "recusou o token")
        assert world.service.credentials.get("home_assistant") is None


async def test_a_good_home_assistant_token_is_saved(world, monkeypatch):
    checked = []
    monkeypatch.setattr(
        house_page,
        "verify_connection",
        lambda url, token: checked.append((url, token)),
    )
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        user.find("Token de acesso").type("token-bom-1234")
        user.find(kind=ui.button, content="Validar e salvar o token").click()

        assert await notified(user, "Token válido e salvo")
        assert checked == [("http://localhost:8123", "token-bom-1234")]
        assert world.service.credentials.get("home_assistant") == "token-bom-1234"


async def test_connection_test_reports_the_result(world, monkeypatch):
    monkeypatch.setattr(house_page, "verify_connection", lambda url, token: None)
    world.service.credentials.set("home_assistant", "token-salvo-1234")
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/casa")
        user.find(kind=ui.button, content="Testar conexão").click()

        assert await notified(user, "Conexão com o Home Assistant funcionando")


# ---- Voz e fala


def stub_models(monkeypatch, missing):
    downloads = []
    monkeypatch.setattr(voice_page, "missing_models", lambda settings, data_dir: missing)
    monkeypatch.setattr(
        voice_page,
        "prepare_models",
        lambda settings, data_dir: downloads.append(settings.whisper_model),
    )
    return downloads


async def test_voice_settings_are_applied_to_the_running_voice(world, monkeypatch):
    stub_models(monkeypatch, [])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        element(user, ui.number, "Silêncio que encerra o pedido (segundos)").set_value(1.5)
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        assert world.service.config.voice.silence_seconds == 1.5
        assert world.service.voice.reconfigured[-1].silence_seconds == 1.5


async def test_missing_models_are_downloaded_after_confirming(world, monkeypatch):
    downloads = stub_models(monkeypatch, ["modelo de transcrição 'small' (cerca de 480 MB)"])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        element(user, ui.select, "Modelo do Whisper").set_value("small")
        user.find(kind=ui.button, content="Salvar").click()
        await user.should_see("Baixar agora?")
        user.find(kind=ui.button, content="Baixar").click()

        assert await notified(user, "Salvo")
        assert downloads == ["small"]
        assert world.service.config.voice.whisper_model == "small"


async def test_missing_models_are_not_downloaded_when_declined(world, monkeypatch):
    downloads = stub_models(monkeypatch, ["modelo de transcrição 'small' (cerca de 480 MB)"])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        element(user, ui.select, "Modelo do Whisper").set_value("small")
        user.find(kind=ui.button, content="Salvar").click()
        await user.should_see("Baixar agora?")
        user.find(kind=ui.button, content="Cancelar").click()
        await anyio.sleep(0.3)

        assert downloads == []
        assert world.service.config.voice == VoiceSettings()


async def test_an_invalid_voice_value_is_refused(world, monkeypatch):
    stub_models(monkeypatch, [])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        element(user, ui.number, "Silêncio que encerra o pedido (segundos)").set_value(0)
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "silence_seconds")
        assert world.service.config.voice == VoiceSettings()


async def test_speaking_while_the_reply_arrives_can_be_turned_off(world, monkeypatch):
    stub_models(monkeypatch, [])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        element(user, ui.switch, "Começar a falar antes").set_value(False)
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        assert world.service.config.voice.stream_speech is False
        assert world.service.voice.reconfigured[-1].stream_speech is False


async def test_the_saved_voice_can_be_heard(world, monkeypatch):
    stub_models(monkeypatch, [])
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/voz")
        user.find(kind=ui.button, content="Ouvir a voz salva").click()
        await anyio.sleep(0.3)

        assert len(world.service.voice.said) == 1


# ---- Áudio

DEVICES = [
    SimpleNamespace(index=0, name="Microfone USB", inputs=1, outputs=0),
    SimpleNamespace(index=1, name="Caixa de som", inputs=0, outputs=2),
]


def stub_devices(monkeypatch, devices=DEVICES, error=None):
    def load():
        if error:
            raise error
        return SimpleNamespace(list_devices=lambda: devices)

    monkeypatch.setattr(audio_page, "load_devices", load)


async def test_the_chosen_devices_are_saved_and_applied(world, monkeypatch):
    stub_devices(monkeypatch)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/audio")
        element(user, ui.select, "Entrada").set_value("Microfone USB")
        element(user, ui.select, "Saída").set_value("Caixa de som")
        user.find(kind=ui.button, content="Salvar").click()

        assert await notified(user, "Salvo")
        voice = world.service.config.voice
        assert (voice.input_device, voice.output_device) == ("Microfone USB", "Caixa de som")
        assert world.service.voice.reconfigured[-1].input_device == "Microfone USB"


async def test_each_list_only_offers_devices_of_its_kind(world, monkeypatch):
    stub_devices(monkeypatch)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/audio")

        inputs = element(user, ui.select, "Entrada").options
        outputs = element(user, ui.select, "Saída").options
        assert "Microfone USB" in inputs and "Caixa de som" not in inputs
        assert "Caixa de som" in outputs and "Microfone USB" not in outputs


async def test_audio_without_portaudio_explains_how_to_install(world, monkeypatch):
    stub_devices(monkeypatch, error=SetupError("Falta a biblioteca PortAudio."))
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/audio")

        await user.should_see("Falta a biblioteca PortAudio.")


async def test_the_speaker_can_be_tested(world, monkeypatch):
    stub_devices(monkeypatch)
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/audio")
        user.find(kind=ui.button, content="Testar som").click()
        await anyio.sleep(0.3)

        assert len(world.service.voice.said) == 1


# ---- Segurança


async def test_the_password_can_be_changed(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/seguranca")
        user.find("Senha atual").type(PASSWORD)
        user.find("Nova senha").type("outra-senha-456")
        user.find("Repita a nova senha").type("outra-senha-456")
        user.find(kind=ui.button, content="Alterar a senha").click()

        assert await notified(user, "Senha alterada")
        assert world.auth.verify("outra-senha-456")


async def test_the_password_change_needs_the_current_password(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/seguranca")
        user.find("Senha atual").type("senha-errada-123")
        user.find("Nova senha").type("outra-senha-456")
        user.find("Repita a nova senha").type("outra-senha-456")
        user.find(kind=ui.button, content="Alterar a senha").click()

        assert await notified(user, "senha atual está incorreta")
        assert world.auth.verify(PASSWORD)


async def test_network_access_is_saved_for_the_next_start(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/seguranca")
        element(user, ui.switch, "Permitir acesso").set_value(True)
        element(user, ui.number, "Porta").set_value(9000)
        user.find(kind=ui.button, content="Salvar o acesso").click()

        assert await notified(user, "próxima vez que o Cubô for iniciado")
        panel = world.service.config.panel
        assert (panel.listen, panel.port) == ("network", 9000)


async def test_a_certificate_that_does_not_exist_is_refused(world):
    async with user_simulation(main_file=MAIN_FILE) as user:
        await sign_in(user, world)
        await user.open("/seguranca")
        user.find("Certificado (.pem)").type("/nao/existe.pem")
        user.find("Chave do certificado (.pem)").type("/nao/existe-chave.pem")
        user.find(kind=ui.button, content="Salvar o acesso").click()

        assert await notified(user, "Arquivo não encontrado")
        assert not world.service.config.panel.https
