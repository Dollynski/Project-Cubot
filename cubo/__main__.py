"""Linha de comando do Cubô."""

import argparse
import getpass
import logging
import sys
import threading
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from cubo.bootstrap import Runtime, build_runtime
from cubo.config import CONFIG_FILE_NAME, Config, default_config_dir, load_config, save_config
from cubo.credentials import ENV_VARS, SECRETS_FILE_NAME, CredentialName, CredentialStore
from cubo.errors import SetupError
from cubo.logs import configure_logging
from cubo.migration import migrate_legacy_env
from cubo.tools.home_assistant import HomeAssistantError
from cubo.usage import USAGE_FILE_NAME, UsageTracker
from cubo.voice import load_devices
from cubo.voice.events import Event, Heard, Replied, StateChanged
from cubo.voice.models import DownloadError, default_data_dir, prepare_models

# O protótipo antigo guardava a configuração num .env na pasta do projeto.
LEGACY_ENV_PATH = Path(".env")

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config_dir = default_config_dir()
    credentials = CredentialStore(config_dir / SECRETS_FILE_NAME)
    configure_logging(
        credentials.all_values, level=logging.DEBUG if args.verbose else logging.WARNING
    )
    return args.run(args, config_dir, credentials)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cubo", description="Assistente de voz Cubô.")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra logs detalhados")
    parser.add_argument(
        "--sem-painel", action="store_true", help="não abre o painel web (só a voz)"
    )
    # Sem comando, o Cubô liga o microfone e fica esperando a wake word.
    parser.set_defaults(run=_run_voice_mode)
    commands = parser.add_subparsers(dest="command", title="comandos")

    text = commands.add_parser("texto", help="conversa com o Cubô digitando, sem áudio")
    text.set_defaults(run=_run_text_mode)

    panel = commands.add_parser("painel", help="abre só o painel, sem ligar o microfone")
    panel.set_defaults(run=_run_panel_only)

    prepare = commands.add_parser(
        "preparar", help="baixa os modelos de voz (wake word, transcrição e voz)"
    )
    prepare.set_defaults(run=_run_prepare)

    audio = commands.add_parser("audio", help="lista os microfones e alto-falantes disponíveis")
    audio.set_defaults(run=_run_audio_list)

    key = commands.add_parser("chave", help="salva ou remove uma chave de API ou token")
    key.add_argument("nome", choices=get_args(CredentialName))
    key.add_argument("--remover", action="store_true", help="apaga a credencial salva")
    key.set_defaults(run=_run_key_command)
    return parser


def _run_voice_mode(
    args: argparse.Namespace, config_dir: Path, credentials: CredentialStore
) -> int:
    return _run_service(args, config_dir, credentials, voice=True)


def _run_panel_only(
    args: argparse.Namespace, config_dir: Path, credentials: CredentialStore
) -> int:
    return _run_service(args, config_dir, credentials, voice=False)


def _run_service(
    args: argparse.Namespace, config_dir: Path, credentials: CredentialStore, *, voice: bool
) -> int:
    """Liga o Cubô: a IA, a voz (se ``voice``) e o painel (a menos que ``--sem-painel``)."""
    try:
        config = _load_or_migrate_config(config_dir, credentials)
    except (ValidationError, tomllib.TOMLDecodeError) as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return 2

    # Importados aqui: carregam os modelos de áudio, que os modos de texto e de chave não usam.
    from cubo.service import CuboService
    from cubo.voice.session import VoiceSession

    data_dir = default_data_dir()
    service = CuboService(
        config=config,
        config_path=config_dir / CONFIG_FILE_NAME,
        credentials=credentials,
        data_dir=data_dir,
        usage=UsageTracker(data_dir / USAGE_FILE_NAME),
        voice_factory=VoiceSession if voice else None,
        on_event=_show_event,
    )
    service.start()
    _print_status(service)
    try:
        if args.sem_painel:
            if service.voice is None:
                reason = service.problems.get("voz", "nem o painel nem a voz foram ligados")
                print(f"Erro: {reason}", file=sys.stderr)
                return 2
            print(f"Cubô ouvindo. Diga '{config.voice.wake_word}'; Ctrl+C para sair.")
            _wait_until_interrupted()
        else:
            _run_panel(service, config_dir)
    finally:
        service.stop()
    return 0


def _print_status(service) -> None:
    for message in service.problems.values():
        print(f"Aviso: {message}")
    for warning in service.warnings:
        print(f"Aviso: {warning}")
    runtime = service.runtime
    if runtime is not None and runtime.home_assistant is not None:
        try:
            runtime.home_assistant.check_connection()
        except HomeAssistantError as error:
            print(f"Aviso: {error}")


def _run_panel(service, config_dir: Path) -> None:
    from cubo.web.app import panel_urls, run_panel
    from cubo.web.auth import AUTH_FILE_NAME, LoginThrottle, PanelAuth
    from cubo.web.panel import Panel

    settings = service.config.panel
    auth = PanelAuth(config_dir / AUTH_FILE_NAME)
    print("Painel: " + " ou ".join(panel_urls(settings)))
    if auth.setup_code:
        print(f"Primeiro acesso: o painel vai pedir o código {auth.setup_code}.")
    run_panel(Panel(service, auth, LoginThrottle()), settings, config_dir / "nicegui")


def _wait_until_interrupted() -> None:
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print()


def _show_event(event: Event) -> None:
    match event:
        case StateChanged(state):
            logger.debug("Estado: %s", state)
        case Heard(text):
            print(f"você> {text}")
        case Replied(text):
            print(f"cubô> {text or '(sem resposta)'}")


def _run_text_mode(
    _args: argparse.Namespace, config_dir: Path, credentials: CredentialStore
) -> int:
    opened = _open_runtime(config_dir, credentials)
    if opened is None:
        return 2
    _config, runtime = opened

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


def _open_runtime(config_dir: Path, credentials: CredentialStore) -> tuple[Config, Runtime] | None:
    """Carrega a configuração e monta o assistente. Mostra o erro e devolve ``None`` se falhar."""
    try:
        config = _load_or_migrate_config(config_dir, credentials)
        runtime = build_runtime(config, credentials)
    except (SetupError, ValidationError, tomllib.TOMLDecodeError) as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return None

    for warning in runtime.warnings:
        print(f"Aviso: {warning}")
    if runtime.home_assistant is not None:
        try:
            runtime.home_assistant.check_connection()
        except HomeAssistantError as error:
            print(f"Aviso: {error}")
    return config, runtime


def _run_prepare(_args: argparse.Namespace, config_dir: Path, credentials: CredentialStore) -> int:
    try:
        voice = _load_or_migrate_config(config_dir, credentials).voice
    except (ValidationError, tomllib.TOMLDecodeError) as error:
        print(f"Erro de configuração: {error}", file=sys.stderr)
        return 2

    data_dir = default_data_dir()
    print(f"Os modelos ficam em {data_dir}.")
    try:
        prepare_models(voice, data_dir, print)
    except DownloadError as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    print("Tudo pronto.")
    return 0


def _run_audio_list(
    _args: argparse.Namespace, config_dir: Path, _credentials: CredentialStore
) -> int:
    try:
        devices = load_devices().list_devices()
    except SetupError as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    for device in devices:
        kinds = [
            name for name, count in (("entrada", device.inputs), ("saída", device.outputs)) if count
        ]
        print(f"{device.index:>3}  {device.name} ({', '.join(kinds)})")
    print(
        '\nPara escolher, ponha parte do nome (como "USB") em input_device / output_device, '
        f"na seção [voice] de {config_dir / CONFIG_FILE_NAME}.\n"
        "Prefira o nome: os números mudam quando um dispositivo é ligado ou desligado."
    )
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
