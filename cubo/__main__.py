"""Linha de comando do Cubô."""

import argparse
import getpass
import logging
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from cubo.bootstrap import build_runtime
from cubo.config import CONFIG_FILE_NAME, Config, default_config_dir, load_config, save_config
from cubo.credentials import ENV_VARS, SECRETS_FILE_NAME, CredentialName, CredentialStore
from cubo.llm.factory import SetupError
from cubo.logs import configure_logging
from cubo.migration import migrate_legacy_env
from cubo.tools.home_assistant import HomeAssistantError

# O protótipo antigo guardava a configuração num .env na pasta do projeto.
LEGACY_ENV_PATH = Path(".env")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config_dir = default_config_dir()
    credentials = CredentialStore(config_dir / SECRETS_FILE_NAME)
    configure_logging(
        credentials.all_values, level=logging.DEBUG if args.verbose else logging.WARNING
    )
    if args.command is None:
        parser.print_help()
        return 1
    return args.run(args, config_dir, credentials)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cubo", description="Assistente de voz Cubô.")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra logs detalhados")
    commands = parser.add_subparsers(dest="command", title="comandos")

    text = commands.add_parser("texto", help="conversa com o Cubô digitando, sem áudio")
    text.set_defaults(run=_run_text_mode)

    key = commands.add_parser("chave", help="salva ou remove uma chave de API ou token")
    key.add_argument("nome", choices=get_args(CredentialName))
    key.add_argument("--remover", action="store_true", help="apaga a credencial salva")
    key.set_defaults(run=_run_key_command)
    return parser


def _run_text_mode(
    _args: argparse.Namespace, config_dir: Path, credentials: CredentialStore
) -> int:
    try:
        config = _load_or_migrate_config(config_dir, credentials)
        runtime = build_runtime(config, credentials)
    except (SetupError, ValidationError, tomllib.TOMLDecodeError) as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return 2

    for warning in runtime.warnings:
        print(f"Aviso: {warning}")
    if runtime.home_assistant is not None:
        try:
            runtime.home_assistant.check_connection()
        except HomeAssistantError as error:
            print(f"Aviso: {error}")

    print("Cubô em modo texto. Digite sua mensagem; Ctrl+D para sair.")
    try:
        while True:
            try:
                text = input("você> ").strip()
            except EOFError:
                print()
                break
            if text:
                print(f"cubô> {runtime.assistant.reply(text) or '(sem resposta)'}")
    except KeyboardInterrupt:
        print()
    finally:
        runtime.close()
    return 0


def _run_key_command(
    args: argparse.Namespace, config_dir: Path, credentials: CredentialStore
) -> int:
    name: CredentialName = args.nome
    if args.remover:
        removed = credentials.delete(name)
        print("Credencial removida." if removed else "Não havia credencial salva.")
        return 0

    value = getpass.getpass(f"Cole a credencial de {name} (ela não aparece na tela): ")
    if not value.strip():
        print("Nada foi salvo.")
        return 1
    credentials.set(name, value)
    print(f"Salva em {config_dir / SECRETS_FILE_NAME}: {credentials.masked(name)}")
    print(f"Se a variável {ENV_VARS[name]} estiver definida, ela tem prioridade sobre o arquivo.")
    return 0


def _load_or_migrate_config(config_dir: Path, credentials: CredentialStore) -> Config:
    """Lê o config.toml. Na primeira execução, importa o .env do protótipo, se existir."""
    config_path = config_dir / CONFIG_FILE_NAME
    if config_path.exists() or not LEGACY_ENV_PATH.exists():
        return load_config(config_path)
    config, imported = migrate_legacy_env(LEGACY_ENV_PATH, credentials)
    save_config(config, config_path)
    print(f"Configuração do protótipo importada de {LEGACY_ENV_PATH}: {', '.join(imported)}.")
    return config


if __name__ == "__main__":
    raise SystemExit(main())
