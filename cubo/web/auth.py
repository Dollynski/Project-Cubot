"""Senha do painel: guardada com hash, com bloqueio depois de tentativas erradas."""

import hashlib
import hmac
import math
import secrets
import time
from collections.abc import Callable
from pathlib import Path

from cubo.toml_files import read_toml, write_toml

AUTH_FILE_NAME = "panel.toml"
MIN_PASSWORD_LENGTH = 8

# Parâmetros do scrypt (cerca de 16 MB de memória por conferência, aceitável numa placa pequena).
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16


class PasswordError(ValueError):
    """A senha não serve; a mensagem explica por quê."""


class PanelAuth:
    """Guarda a senha (só o hash) e o segredo que assina as sessões, num arquivo 0600.

    No primeiro acesso, ainda sem senha, a pessoa precisa informar o código de configuração, que
    só aparece no terminal de quem iniciou o Cubô. Assim, alguém na mesma rede não consegue
    definir a senha primeiro.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._setup_code = secrets.token_urlsafe(6)

    @property
    def has_password(self) -> bool:
        return "password" in read_toml(self._path)

    @property
    def setup_code(self) -> str | None:
        """O código do primeiro acesso, enquanto não houver senha."""
        return None if self.has_password else self._setup_code

    def check_setup_code(self, code: str) -> bool:
        return not self.has_password and hmac.compare_digest(code.strip(), self._setup_code)

    def set_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise PasswordError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        salt = secrets.token_bytes(SALT_BYTES)
        data = read_toml(self._path)
        data["password"] = {
            "salt": salt.hex(),
            "hash": _hash(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P).hex(),
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
        }
        write_toml(self._path, data, mode=0o600)

    def verify(self, password: str) -> bool:
        stored = read_toml(self._path).get("password")
        if not stored:
            return False
        digest = _hash(
            password, bytes.fromhex(stored["salt"]), stored["n"], stored["r"], stored["p"]
        )
        return hmac.compare_digest(digest, bytes.fromhex(stored["hash"]))

    def clear_password(self) -> bool:
        """Esquece a senha (e as sessões abertas). Retorna ``False`` se não havia senha."""
        data = read_toml(self._path)
        if "password" not in data:
            return False
        del data["password"]
        data.pop("session_secret", None)
        write_toml(self._path, data, mode=0o600)
        return True

    def session_secret(self) -> str:
        """Segredo que assina as sessões; é criado na primeira vez e reaproveitado depois."""
        data = read_toml(self._path)
        if not data.get("session_secret"):
            data["session_secret"] = secrets.token_hex(32)
            write_toml(self._path, data, mode=0o600)
        return str(data["session_secret"])


def _hash(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)


class LoginThrottle:
    """Bloqueia quem errou a senha vezes demais, por um tempo, para impedir adivinhação."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        lock_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._lock_seconds = lock_seconds
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def seconds_locked(self, client: str) -> int:
        """Quanto tempo falta para o cliente poder tentar de novo (zero se já pode)."""
        remaining = self._locked_until.get(client, 0.0) - self._clock()
        if remaining <= 0:
            self._locked_until.pop(client, None)
            return 0
        return math.ceil(remaining)

    def fail(self, client: str) -> None:
        failures = self._failures.get(client, 0) + 1
        if failures >= self._max_attempts:
            self._locked_until[client] = self._clock() + self._lock_seconds
            failures = 0
        self._failures[client] = failures

    def succeed(self, client: str) -> None:
        self._failures.pop(client, None)
        self._locked_until.pop(client, None)
