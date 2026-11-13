"""Chaves de API e tokens, guardados em ``secrets.toml``, separado da configuração."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, get_args

from cubo.toml_files import read_toml, write_toml

CredentialName = Literal["gemini", "claude", "openai", "home_assistant"]

SECRETS_FILE_NAME = "secrets.toml"

ENV_VARS: dict[CredentialName, str] = {
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "home_assistant": "HOME_ASSISTANT_TOKEN",
}

_MASK = "••••"


class CredentialStore:
    """Lê e grava credenciais. A variável de ambiente correspondente tem prioridade sobre o arquivo.

    O arquivo é criado com permissão 0600 (só o dono lê). O conteúdo fica em cache e é
    atualizado a cada gravação feita por esta instância.
    """

    def __init__(self, path: Path, environ: Mapping[str, str] = os.environ) -> None:
        self._path = path
        self._environ = environ
        self._cache: dict[str, str] | None = None

    def get(self, name: CredentialName) -> str | None:
        _validate(name)
        return self._environ.get(ENV_VARS[name]) or self._stored().get(name) or None

    def set(self, name: CredentialName, value: str) -> None:
        _validate(name)
        if not value.strip():
            raise ValueError("a credencial não pode ser vazia")
        self._write({**self._stored(), name: value.strip()})

    def delete(self, name: CredentialName) -> bool:
        """Apaga a credencial do arquivo. Retorna ``False`` se ela não estava lá."""
        _validate(name)
        stored = self._stored()
        if name not in stored:
            return False
        self._write({key: value for key, value in stored.items() if key != name})
        return True

    def masked(self, name: CredentialName) -> str | None:
        """Mostra só os 4 últimos caracteres, para exibir sem revelar a credencial."""
        value = self.get(name)
        return f"{_MASK}{value[-4:]}" if value else None

    def all_values(self) -> list[str]:
        """Todas as credenciais conhecidas, para o filtro de logs mascarar."""
        from_env = (self._environ.get(variable) for variable in ENV_VARS.values())
        return [value for value in (*from_env, *self._stored().values()) if value]

    def _stored(self) -> dict[str, str]:
        if self._cache is None:
            self._cache = {key: str(value) for key, value in read_toml(self._path).items()}
        return self._cache

    def _write(self, data: dict[str, str]) -> None:
        write_toml(self._path, data, mode=0o600)
        self._cache = dict(data)


def _validate(name: str) -> None:
    if name not in get_args(CredentialName):
        raise ValueError(f"credencial desconhecida: {name}")
