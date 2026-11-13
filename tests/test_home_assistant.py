import json

import httpx2
import pytest

from cubo.config import Device
from cubo.tools.home_assistant import HomeAssistantClient, HomeAssistantError, HomeAssistantTools
from cubo.tools.registry import ToolRegistry

SERVICE_RESULT = {"turn_on": "on", "turn_off": "off"}


class FakeHomeAssistant:
    """Simula a API REST do Home Assistant em memória."""

    def __init__(self, states, *, lag_reads=0, stuck=False, status=200):
        self.states = {entity_id: dict(state) for entity_id, state in states.items()}
        self.lag_reads = lag_reads  # leituras até o novo estado aparecer
        self.stuck = stuck  # o dispositivo nunca muda de estado
        self.status = status
        self.service_calls = []
        self._pending = None

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        if request.headers.get("Authorization") != "Bearer token-teste":
            return httpx2.Response(401)
        if self.status != 200:
            return httpx2.Response(self.status)
        path = request.url.path
        if path == "/api/":
            return httpx2.Response(200, json={"message": "API running."})
        if path.startswith("/api/states/"):
            return self._read(path.removeprefix("/api/states/"))
        if path.startswith("/api/services/"):
            domain, service = path.removeprefix("/api/services/").split("/")
            return self._call(domain, service, json.loads(request.content))
        return httpx2.Response(404)

    def _read(self, entity_id):
        if entity_id not in self.states:
            return httpx2.Response(404)
        if self._pending and self._pending[0] == entity_id:
            reads_left = self._pending[2] - 1
            if reads_left < 0:
                self.states[entity_id]["state"] = self._pending[1]
                self._pending = None
            else:
                self._pending = (entity_id, self._pending[1], reads_left)
        return httpx2.Response(200, json={"entity_id": entity_id, **self.states[entity_id]})

    def _call(self, domain, service, data):
        self.service_calls.append((domain, service, data))
        entity_id = data["entity_id"]
        current = self.states[entity_id]["state"]
        new_state = SERVICE_RESULT.get(service) or ("off" if current == "on" else "on")
        if self.stuck:
            return httpx2.Response(200, json=[])
        if self.lag_reads:
            self._pending = (entity_id, new_state, self.lag_reads)
            return httpx2.Response(200, json=[])
        self.states[entity_id]["state"] = new_state
        return httpx2.Response(200, json=[{"entity_id": entity_id, **self.states[entity_id]}])


DEVICES = [
    Device(entity_id="light.sala", alias="luz da sala"),
    Device(entity_id="switch.cafeteira", alias="cafeteira"),
    Device(entity_id="input_boolean.lampada_led", alias="luz do quarto"),
    Device(entity_id="sensor.temperatura_quarto", alias="temperatura do quarto"),
    Device(entity_id="weather.forecast_home", alias="previsão do tempo"),
]

STATES = {
    "light.sala": {"state": "off", "attributes": {}},
    "switch.cafeteira": {"state": "on", "attributes": {}},
    "input_boolean.lampada_led": {"state": "off", "attributes": {}},
    "sensor.temperatura_quarto": {
        "state": "23.5",
        "attributes": {"unit_of_measurement": "°C"},
    },
    "weather.forecast_home": {
        "state": "partlycloudy",
        "attributes": {"temperature": 28, "temperature_unit": "°C", "humidity": 60},
    },
}


def make_registry(fake, sleeps=None):
    http = httpx2.Client(transport=httpx2.MockTransport(fake.handle))
    client = HomeAssistantClient("http://ha.local:8123/", "token-teste", http=http)
    tools = HomeAssistantTools(
        client, DEVICES, sleep=(sleeps.append if sleeps is not None else lambda _: None)
    )
    return ToolRegistry(tools.build())


def test_turns_on_a_light_with_brightness_using_the_light_domain():
    fake = FakeHomeAssistant(STATES)
    registry = make_registry(fake)

    outcome = registry.run(
        "controlar_dispositivo", {"dispositivo": "luz da sala", "acao": "ligar", "brilho": 40}
    )

    assert not outcome.is_error
    assert json.loads(outcome.content) == {"dispositivo": "luz da sala", "estado": "ligado"}
    assert fake.service_calls == [
        ("light", "turn_on", {"entity_id": "light.sala", "brightness_pct": 40})
    ]


@pytest.mark.parametrize(
    ("alias", "action", "expected_call", "expected_state"),
    [
        ("cafeteira", "desligar", ("switch", "turn_off"), "desligado"),
        ("luz do quarto", "alternar", ("input_boolean", "toggle"), "ligado"),
    ],
)
def test_service_follows_the_entity_domain(alias, action, expected_call, expected_state):
    fake = FakeHomeAssistant(STATES)

    outcome = make_registry(fake).run(
        "controlar_dispositivo", {"dispositivo": alias, "acao": action}
    )

    assert json.loads(outcome.content)["estado"] == expected_state
    assert fake.service_calls[0][:2] == expected_call


def test_waits_for_a_slow_device_to_report_the_new_state():
    fake = FakeHomeAssistant(STATES, lag_reads=2)
    sleeps = []

    outcome = make_registry(fake, sleeps).run(
        "controlar_dispositivo", {"dispositivo": "luz da sala", "acao": "ligar"}
    )

    assert not outcome.is_error
    assert len(sleeps) == 2


def test_reports_failure_when_the_state_does_not_change():
    fake = FakeHomeAssistant(STATES, stuck=True)

    outcome = make_registry(fake).run(
        "controlar_dispositivo", {"dispositivo": "luz da sala", "acao": "ligar"}
    )

    assert outcome.is_error
    assert "luz da sala continua desligado" in outcome.content


def test_brightness_is_only_for_lights():
    fake = FakeHomeAssistant(STATES)

    outcome = make_registry(fake).run(
        "controlar_dispositivo", {"dispositivo": "cafeteira", "acao": "ligar", "brilho": 50}
    )

    assert outcome.is_error
    assert fake.service_calls == []


def test_reads_a_sensor_with_its_unit():
    outcome = make_registry(FakeHomeAssistant(STATES)).run(
        "ler_estado", {"dispositivo": "temperatura do quarto"}
    )

    assert json.loads(outcome.content) == {
        "dispositivo": "temperatura do quarto",
        "estado": "23.5",
        "unidade": "°C",
    }


def test_weather_reading_says_it_is_an_outdoor_forecast():
    outcome = make_registry(FakeHomeAssistant(STATES)).run(
        "ler_estado", {"dispositivo": "previsão do tempo"}
    )

    reading = json.loads(outcome.content)
    assert reading["origem"] == "previsão do tempo (área externa)"
    assert reading["temperatura"] == 28


def test_control_tool_only_lists_controllable_devices():
    registry = make_registry(FakeHomeAssistant(STATES))
    control = next(tool for tool in registry if tool.name == "controlar_dispositivo")

    assert control.parameters["properties"]["dispositivo"]["enum"] == [
        "luz da sala",
        "cafeteira",
        "luz do quarto",
    ]


def test_unknown_device_is_an_error():
    outcome = make_registry(FakeHomeAssistant(STATES)).run("ler_estado", {"dispositivo": "garagem"})

    assert outcome.is_error
    assert "garagem" in outcome.content


def test_rejected_token_has_a_clear_message():
    http = httpx2.Client(transport=httpx2.MockTransport(FakeHomeAssistant(STATES).handle))
    client = HomeAssistantClient("http://ha.local:8123", "token-errado", http=http)

    with pytest.raises(HomeAssistantError, match="recusou o token"):
        client.check_connection()


def test_unreachable_server_has_a_clear_message():
    def refuse(request):
        raise httpx2.ConnectError("conexão recusada", request=request)

    client = HomeAssistantClient(
        "http://ha.local:8123",
        "token-teste",
        http=httpx2.Client(transport=httpx2.MockTransport(refuse)),
    )

    with pytest.raises(HomeAssistantError, match="não respondeu em http://ha.local:8123"):
        client.check_connection()
