"""Ferramentas e respostas falsas compartilhadas pelos testes dos provedores."""

import httpx2

from cubo.config import VoiceSettings
from cubo.tools.registry import Tool, ToolError, ToolRegistry

REQUEST = httpx2.Request("POST", "https://api.example/v1")


def http_response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=REQUEST)


def home_tools() -> ToolRegistry:
    """Uma ferramenta que funciona e outra que sempre falha."""

    def read(arguments):
        return f"{arguments['dispositivo']}: ligado"

    def broken(_arguments):
        raise ToolError("dispositivo indisponível")

    return ToolRegistry(
        [
            Tool("ler_estado", "Lê o estado.", {"type": "object"}, read),
            Tool("quebrada", "Sempre falha.", {"type": "object"}, broken),
        ]
    )


class FakeRuntime:
    def __init__(self, label):
        self.assistant = f"assistente {label}"
        self.warnings = [f"aviso {label}"]
        self.closed = False

    def close(self):
        self.closed = True


class FakeRuntimeFactory:
    def __init__(self):
        self.runtimes = []
        self.fail_with = None

    def __call__(self, config, credentials, usage):
        if self.fail_with:
            raise self.fail_with
        runtime = FakeRuntime(len(self.runtimes) + 1)
        self.runtimes.append(runtime)
        return runtime


class FakeVoice:
    def __init__(self, assistant):
        self.assistant = assistant
        self.warnings = ["aviso de voz"]
        self.started = self.stopped = False
        self.reconfigured = []
        self.reconfigure_error = None
        self.current = VoiceSettings()
        self.running = True
        self.mic_level = 0.0
        self.error = None
        self.said = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def set_assistant(self, assistant):
        self.assistant = assistant

    def say(self, text):
        self.said.append(text)

    def beep(self):
        pass

    def reconfigure(self, settings):
        if self.reconfigure_error:
            raise self.reconfigure_error
        self.reconfigured.append(settings)
        changed = ["voz"] if settings != self.current else []
        self.current = settings
        return changed


class FakeVoiceFactory:
    def __init__(self):
        self.sessions = []
        self.fail_with = None

    def __call__(self, settings, assistant, data_dir, on_event):
        if self.fail_with:
            raise self.fail_with
        session = FakeVoice(assistant)
        session.on_event = on_event
        self.sessions.append(session)
        return session
