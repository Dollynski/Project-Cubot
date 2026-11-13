"""Ferramentas do Home Assistant: controlar e consultar os dispositivos cadastrados."""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx2

from cubo.config import Device
from cubo.tools.registry import Tool, ToolError

TIMEOUT_SECONDS = 5.0

ACTIONS = {"ligar": "turn_on", "desligar": "turn_off", "alternar": "toggle"}
CONTROLLABLE_DOMAINS = frozenset({"light", "switch", "input_boolean", "fan"})
STATE_NAMES = {
    "on": "ligado",
    "off": "desligado",
    "unavailable": "indisponível",
    "unknown": "desconhecido",
}


class HomeAssistantError(ToolError):
    """Falha ao falar com o Home Assistant, com mensagem pronta para o usuário."""


@dataclass(frozen=True)
class EntityState:
    entity_id: str
    state: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "EntityState":
        return cls(data["entity_id"], str(data["state"]), data.get("attributes") or {})


class HomeAssistantClient:
    """Cliente mínimo da API REST do Home Assistant."""

    def __init__(self, base_url: str, token: str, *, http: httpx2.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx2.Client(timeout=TIMEOUT_SECONDS)
        self._headers = {"Authorization": f"Bearer {token}"}

    def check_connection(self) -> None:
        """Levanta ``HomeAssistantError`` se o endereço ou o token estiverem errados."""
        self._request("GET", "/api/")

    def get_state(self, entity_id: str) -> EntityState:
        return EntityState.from_api(self._request("GET", f"/api/states/{entity_id}").json())

    def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> list[EntityState]:
        """Chama o serviço e devolve os estados que mudaram durante a chamada."""
        response = self._request("POST", f"/api/services/{domain}/{service}", json=dict(data))
        return [EntityState.from_api(item) for item in response.json()]

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **options: Any) -> httpx2.Response:
        try:
            response = self._http.request(
                method, f"{self._base_url}{path}", headers=self._headers, **options
            )
        except httpx2.TransportError as error:
            raise HomeAssistantError(
                f"O Home Assistant não respondeu em {self._base_url}."
            ) from error
        if response.status_code == 401:
            raise HomeAssistantError("O Home Assistant recusou o token (inválido ou expirado).")
        if response.status_code == 404:
            raise HomeAssistantError(f"O Home Assistant não encontrou {path}.")
        if response.is_error:
            raise HomeAssistantError(
                f"O Home Assistant respondeu com erro HTTP {response.status_code}."
            )
        return response


def verify_connection(base_url: str, token: str) -> None:
    """Confere o endereço e o token com uma chamada de teste.

    Levanta ``HomeAssistantError`` com a explicação se algo estiver errado.
    """
    client = HomeAssistantClient(base_url, token)
    try:
        client.check_connection()
    finally:
        client.close()


class HomeAssistantTools:
    """Monta as ferramentas da IA para os dispositivos cadastrados."""

    def __init__(
        self,
        client: HomeAssistantClient,
        devices: Sequence[Device],
        *,
        confirm_attempts: int = 5,
        confirm_interval_seconds: float = 0.4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._devices = list(devices)
        self._controllable = [d for d in devices if d.domain in CONTROLLABLE_DOMAINS]
        self._confirm_attempts = confirm_attempts
        self._confirm_interval = confirm_interval_seconds
        self._sleep = sleep

    def build(self) -> list[Tool]:
        tools = []
        if self._controllable:
            tools.append(self._control_tool())
        if self._devices:
            tools.append(self._read_tool())
        return tools

    def _control_tool(self) -> Tool:
        properties: dict[str, Any] = {
            "dispositivo": {
                "type": "string",
                "enum": [device.alias for device in self._controllable],
                "description": "Nome do dispositivo.",
            },
            "acao": {"type": "string", "enum": list(ACTIONS)},
        }
        if any(device.domain == "light" for device in self._controllable):
            properties["brilho"] = {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Brilho em porcentagem. Só para luzes, com a ação ligar.",
            }
        return Tool(
            name="controlar_dispositivo",
            description=(
                "Liga, desliga ou alterna um dispositivo da casa. "
                "Responde com o estado confirmado pelo Home Assistant."
            ),
            parameters={
                "type": "object",
                "properties": properties,
                "required": ["dispositivo", "acao"],
                "additionalProperties": False,
            },
            handler=self._control,
        )

    def _read_tool(self) -> Tool:
        return Tool(
            name="ler_estado",
            description=(
                "Consulta o estado atual de um dispositivo ou sensor da casa, "
                "como uma luz ou a temperatura."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dispositivo": {
                        "type": "string",
                        "enum": [device.alias for device in self._devices],
                        "description": "Nome do dispositivo.",
                    }
                },
                "required": ["dispositivo"],
                "additionalProperties": False,
            },
            handler=self._read,
        )

    def _control(self, arguments: Mapping[str, Any]) -> str:
        device = _find(self._controllable, arguments.get("dispositivo"))
        action = arguments.get("acao")
        if action not in ACTIONS:
            raise ToolError(f"Ação inválida: {action}. Use ligar, desligar ou alternar.")

        data: dict[str, Any] = {"entity_id": device.entity_id}
        brightness = arguments.get("brilho")
        if brightness is not None:
            if device.domain != "light" or action != "ligar":
                raise ToolError("O brilho só vale para luzes, com a ação ligar.")
            data["brightness_pct"] = int(brightness)

        current = self._client.get_state(device.entity_id) if action == "alternar" else None
        expected = _expected_state(action, current)
        changed = self._client.call_service(device.domain, ACTIONS[action], data)
        final = self._wait_for_state(device.entity_id, expected, changed)
        if final.state != expected:
            raise ToolError(
                f"O Home Assistant aceitou o comando, mas {device.alias} "
                f"continua {_state_name(final.state)}."
            )
        return json.dumps(
            {"dispositivo": device.alias, "estado": _state_name(final.state)}, ensure_ascii=False
        )

    def _read(self, arguments: Mapping[str, Any]) -> str:
        device = _find(self._devices, arguments.get("dispositivo"))
        state = self._client.get_state(device.entity_id)
        return json.dumps(_describe(device, state), ensure_ascii=False)

    def _wait_for_state(
        self, entity_id: str, expected: str, changed: Sequence[EntityState]
    ) -> EntityState:
        """Confirma o novo estado: pela resposta do serviço ou consultando de novo.

        Alguns dispositivos demoram a reportar a mudança, então a consulta se repete algumas vezes.
        """
        reported = next((state for state in changed if state.entity_id == entity_id), None)
        if reported is not None and reported.state == expected:
            return reported
        state = self._client.get_state(entity_id)
        for _ in range(self._confirm_attempts):
            if state.state == expected:
                break
            self._sleep(self._confirm_interval)
            state = self._client.get_state(entity_id)
        return state


def _find(devices: Sequence[Device], alias: object) -> Device:
    wanted = str(alias).casefold()
    for device in devices:
        if device.alias.casefold() == wanted:
            return device
    raise ToolError(f"Dispositivo desconhecido: {alias}.")


def _expected_state(action: str, current: EntityState | None) -> str:
    if action == "alternar":
        return "off" if current is not None and current.state == "on" else "on"
    return "on" if action == "ligar" else "off"


def _state_name(state: str) -> str:
    return STATE_NAMES.get(state, state)


def _describe(device: Device, state: EntityState) -> dict[str, Any]:
    attributes = state.attributes
    description: dict[str, Any] = {
        "dispositivo": device.alias,
        "estado": _state_name(state.state),
    }
    if unit := attributes.get("unit_of_measurement"):
        description["unidade"] = unit
    if device.domain == "light" and attributes.get("brightness") is not None:
        description["brilho_pct"] = round(attributes["brightness"] * 100 / 255)
    if device.domain == "weather":
        # A entidade de clima traz a previsão externa, não a temperatura do cômodo.
        description["origem"] = "previsão do tempo (área externa)"
        for source, target in (
            ("temperature", "temperatura"),
            ("temperature_unit", "unidade_temperatura"),
            ("humidity", "umidade_pct"),
        ):
            if attributes.get(source) is not None:
                description[target] = attributes[source]
    return description
