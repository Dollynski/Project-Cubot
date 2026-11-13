"""O Cubô rodando: IA, Home Assistant e voz, cada parte recarregável sem reiniciar o resto."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from cubo.activity import ActivityLog
from cubo.bootstrap import Runtime, build_runtime
from cubo.config import Config, VoiceSettings, save_config
from cubo.credentials import CredentialName, CredentialStore
from cubo.errors import SetupError
from cubo.usage import UsageTracker
from cubo.voice.events import Event
from cubo.voice.loop import Replier

logger = logging.getLogger(__name__)

AI_PROBLEM = "ia"
LIMITS_PART = "limites de chamadas"
ASSISTANT_PART = "IA e Home Assistant"
LIMIT_FIELDS = {"max_calls_per_minute", "max_calls_per_day"}
VOICE_PROBLEM = "voz"

AI_UNAVAILABLE_SPEECH = (
    "A IA ainda não está configurada. Abra o painel do Cubô para escolher o provedor e a chave."
)


class VoiceFactory(Protocol):
    def __call__(
        self,
        settings: VoiceSettings,
        assistant: Replier,
        data_dir: Path,
        on_event: Callable[[Event], None],
    ): ...


class AssistantUnavailable:
    """Responde que a IA não está pronta, para a voz continuar funcionando enquanto isso."""

    def reply(self, user_text: str, on_text: Callable[[str], None] | None = None) -> str:
        return AI_UNAVAILABLE_SPEECH


class CuboService:
    """Dono de tudo o que roda. O painel só pede mudanças a ele.

    As falhas de IA e de voz não derrubam o serviço: ficam em ``problems`` para o painel mostrar,
    e a pessoa corrige pela própria interface.
    """

    def __init__(
        self,
        *,
        config: Config,
        config_path: Path,
        credentials: CredentialStore,
        data_dir: Path,
        usage: UsageTracker,
        voice_factory: VoiceFactory | None,
        activity: ActivityLog | None = None,
        on_event: Callable[[Event], None] | None = None,
        runtime_factory: Callable[..., Runtime] = build_runtime,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.usage = usage
        self.activity = activity or ActivityLog()
        self.problems: dict[str, str] = {}
        self.runtime: Runtime | None = None
        self.voice = None  # VoiceSession, quando a voz está ligada
        self._config_path = config_path
        self._data_dir = data_dir
        self._voice_factory = voice_factory
        self._listener = on_event
        self._runtime_factory = runtime_factory
        self._lock = threading.RLock()

    @property
    def voice_enabled(self) -> bool:
        return self._voice_factory is not None

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def warnings(self) -> list[str]:
        runtime = self.runtime.warnings if self.runtime else []
        voice = self.voice.warnings if self.voice else []
        return [*runtime, *voice]

    def start(self) -> None:
        with self._lock:
            self._apply_limits(self.config)
            self._install_runtime(self._try_build_runtime(self.config))
            self._start_voice()

    def stop(self) -> None:
        with self._lock:
            if self.voice is not None:
                self.voice.stop()
            if self.runtime is not None:
                self.runtime.close()

    def apply(self, new: Config) -> list[str]:
        """Aplica e salva a configuração, recarregando só o que mudou. Retorna o que recarregou.

        Se algo não carregar (modelo ausente, dispositivo inexistente), levanta ``SetupError``
        e nada muda: a configuração não é salva.
        """
        with self._lock:
            runtime = self._runtime_for(self.config, new)
            reloaded = [ASSISTANT_PART] if runtime is not None else []
            if _limits(self.config) != _limits(new):
                reloaded.append(LIMITS_PART)

            try:
                if self.voice is not None:
                    reloaded += self.voice.reconfigure(new.voice)
            except SetupError:
                if runtime is not None:
                    runtime.close()
                raise

            self.config = new
            self._apply_limits(new)
            save_config(new, self._config_path)
            if runtime is not None:
                self._install_runtime(runtime)
            if self.voice is None:
                self._start_voice()
            return reloaded

    def _runtime_for(self, old: Config, new: Config) -> Runtime | None:
        """O assistente novo, se for preciso trocá-lo; ``None`` se o atual continua valendo."""
        if _llm_inputs(old) != _llm_inputs(new):
            # Quem mudou o provedor ou o modelo precisa saber, na hora, se a IA não carrega.
            return self._runtime_factory(new, self.credentials, self.usage)
        if self.runtime is None or old.home_assistant != new.home_assistant:
            # A IA não foi mexida: se ela já estava fora do ar, isso não barra a mudança.
            return self._try_build_runtime(new)
        return None

    def save_credential(self, name: CredentialName, value: str) -> None:
        """Guarda a credencial (o chamador já a validou) e recarrega o que depende dela."""
        with self._lock:
            self.credentials.set(name, value)
            self.reload_assistant()

    def delete_credential(self, name: CredentialName) -> None:
        with self._lock:
            self.credentials.delete(name)
            self.reload_assistant()

    def reload_assistant(self) -> None:
        with self._lock:
            self._install_runtime(self._try_build_runtime(self.config))

    def restart_voice(self) -> None:
        with self._lock:
            if self.voice is not None:
                self.voice.stop()
                self.voice = None
            self._start_voice()

    def _apply_limits(self, config: Config) -> None:
        self.usage.set_limits(
            max_calls_per_minute=config.llm.max_calls_per_minute,
            max_calls_per_day=config.llm.max_calls_per_day,
        )

    def _try_build_runtime(self, config: Config) -> Runtime | None:
        try:
            runtime = self._runtime_factory(config, self.credentials, self.usage)
        except SetupError as error:
            self.problems[AI_PROBLEM] = str(error)
            return None
        self.problems.pop(AI_PROBLEM, None)
        return runtime

    def _install_runtime(self, runtime: Runtime | None) -> None:
        old, self.runtime = self.runtime, runtime
        if old is not None:
            old.close()
        if runtime is not None:
            self.problems.pop(AI_PROBLEM, None)
        if self.voice is not None:
            self.voice.set_assistant(self._assistant())

    def _assistant(self) -> Replier:
        return self.runtime.assistant if self.runtime else AssistantUnavailable()

    def _start_voice(self) -> None:
        if self._voice_factory is None:
            return
        try:
            session = self._voice_factory(
                self.config.voice, self._assistant(), self._data_dir, self._on_event
            )
            session.start()
        except SetupError as error:
            self.problems[VOICE_PROBLEM] = str(error)
            return
        self.voice = session
        self.problems.pop(VOICE_PROBLEM, None)

    def _on_event(self, event: Event) -> None:
        self.activity.record(event)
        if self._listener is not None:
            self._listener(event)


def _llm_inputs(config: Config) -> dict:
    """As configurações da IA que exigem montar o assistente de novo (os limites não exigem)."""
    return config.llm.model_dump(exclude=LIMIT_FIELDS)


def _limits(config: Config) -> dict:
    return config.llm.model_dump(include=LIMIT_FIELDS)
