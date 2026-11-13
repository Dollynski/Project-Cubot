"""Leitura e gravação atômica de arquivos TOML."""

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w


def read_toml(path: Path) -> dict[str, Any]:
    """Lê um arquivo TOML; um arquivo inexistente vale como vazio."""
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def write_toml(path: Path, data: dict[str, Any], *, mode: int) -> None:
    """Grava ``data`` em ``path`` com a permissão ``mode``, sem deixar arquivo pela metade.

    O conteúdo vai primeiro para um arquivo temporário criado já com a permissão final,
    e só então substitui o original.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "wb") as file:
        tomli_w.dump(data, file)
    os.chmod(temporary, mode)
    os.replace(temporary, path)
