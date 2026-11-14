#!/usr/bin/env bash
# Instala o Cubô como serviço do usuário (systemd): sobe no boot e reinicia se cair.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$INSTALL_DIR/.venv"
UNIT_NAME="cubo.service"
HOSTNAME_PATTERN='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'
WAIT_SECONDS=90

# shellcheck source=deploy/common.sh
source "$SCRIPT_DIR/common.sh"

OPEN_NETWORK=0
NEW_HOSTNAME=""
WITH_ESPEAK=1
WITH_AVAHI=1
WITH_MODELS=1
SHOW_UNIT=0

usage() {
  cat <<'TEXTO'
Uso: deploy/install.sh [opções]

Instala as dependências do sistema, o Cubô e a unidade do systemd, e liga o serviço.
Rodar de novo atualiza (depois de um `git pull`) e reinicia o serviço.

Opções:
  --rede             libera o painel para a rede (celular, outro PC) e gera um
                     certificado HTTPS próprio, para a senha não viajar aberta
  --hostname NOME    troca o nome da máquina para NOME (pede confirmação), para
                     abrir o painel em NOME.local
  --sem-espeak       não instala o espeak-ng (voz de reserva)
  --sem-avahi        não instala o avahi (o endereço NOME.local)
  --sem-modelos      não baixa os modelos de voz agora (veja `cubo preparar`)
  --sim              não pergunta nada, responde sim
  --simular          só mostra o que faria, sem mudar nada
  --mostrar-unidade  mostra a unidade do systemd que seria instalada e sai
  -h, --ajuda        mostra esta ajuda
TEXTO
}

parse_args() {
  while (($#)); do
    case "$1" in
      --rede) OPEN_NETWORK=1 ;;
      --hostname)
        (($# >= 2)) || usage_error "--hostname precisa de um nome."
        NEW_HOSTNAME="$2"
        shift
        ;;
      --sem-espeak) WITH_ESPEAK=0 ;;
      --sem-avahi) WITH_AVAHI=0 ;;
      --sem-modelos) WITH_MODELS=0 ;;
      --sim) ASSUME_YES=1 ;;
      --simular) SIMULATE=1 ;;
      --mostrar-unidade) SHOW_UNIT=1 ;;
      -h | --ajuda)
        usage
        exit 0
        ;;
      *) usage_error "opção desconhecida: $1" ;;
    esac
    shift
  done
  if [[ -n "$NEW_HOSTNAME" && ! "$NEW_HOSTNAME" =~ $HOSTNAME_PATTERN ]]; then
    usage_error "nome de máquina inválido: $NEW_HOSTNAME (use letras minúsculas, números e hífen)."
  fi
}

# O texto da unidade, com a pasta do projeto no lugar do marcador.
render_unit() {
  # O systemd interpreta o % no caminho, então ele é dobrado (o $ não: no caminho do executável
  # ele ficaria literal e o arquivo não seria achado). O resto protege o sed.
  local folder="${INSTALL_DIR//%/%%}"
  folder="${folder//[&|\\]/\\&}"
  sed "s|@INSTALL_DIR@|$folder|g" "$SCRIPT_DIR/cubo.service"
}

check_system() {
  command -v apt-get >/dev/null ||
    fail "este script usa o apt (Debian, Ubuntu, Armbian). Em outro sistema, instale à mão: python3-venv, libportaudio2 (e, se quiser, espeak-ng e avahi)."
  command -v systemctl >/dev/null || fail "o systemd não foi encontrado."
  command -v python3 >/dev/null || fail "o python3 não foi encontrado."
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    fail "o Cubô precisa do Python 3.11 ou mais novo, e aqui há $(python3 -V 2>&1). No Debian 12 e no Armbian Bookworm o python3 já serve; no Ubuntu 22.04 é preciso instalar outro Python."
  fi
}

install_packages() {
  say "Dependências do sistema"
  local packages=(python3-venv libportaudio2)
  if ((WITH_ESPEAK)); then packages+=(espeak-ng); fi
  if ((WITH_AVAHI)); then packages+=(avahi-daemon); fi
  if ((OPEN_NETWORK)); then packages+=(openssl); fi
  run sudo apt-get install -y "${packages[@]}"
}

install_app() {
  say "Cubô"
  run python3 -m venv "$VENV"
  run "$VENV/bin/pip" install --quiet -e "$INSTALL_DIR"
  if ((WITH_MODELS)); then
    say "Modelos de voz (cerca de 215 MB na primeira vez)"
    run "$VENV/bin/cubo" preparar
  fi
}

set_hostname() {
  [[ -n "$NEW_HOSTNAME" ]] || return 0
  local current
  current="$(hostname)"
  if [[ "$current" == "$NEW_HOSTNAME" ]]; then
    return 0
  fi
  say "Nome da máquina"
  if ! confirm "Trocar o nome da máquina de '$current' para '$NEW_HOSTNAME'?"; then
    note "Mantido '$current'. Sem a troca, o painel abre em $current.local."
    NEW_HOSTNAME=""
    return 0
  fi
  run sudo hostnamectl set-hostname "$NEW_HOSTNAME"
  # No Debian, o nome antigo continua na linha 127.0.1.1 e o sudo passa a reclamar dele.
  if grep -q '^127\.0\.1\.1[[:space:]]' /etc/hosts 2>/dev/null; then
    run sudo sed -i.cubo-bak "/^127\\.0\\.1\\.1[[:space:]]/s/\\b${current}\\b/${NEW_HOSTNAME}/" /etc/hosts
  fi
  if ((WITH_AVAHI)); then run sudo systemctl restart avahi-daemon; fi
}

enable_network() {
  ((OPEN_NETWORK)) || return 0
  say "Painel na rede, com HTTPS"
  local tls certificate key name
  tls="$(config_dir)/tls"
  certificate="$tls/certificado.pem"
  key="$tls/chave.pem"
  name="${NEW_HOSTNAME:-$(hostname)}"
  run mkdir -p "$tls"
  run chmod 700 "$tls"
  if [[ -f "$certificate" && -f "$key" ]]; then
    note "Reaproveitando o certificado de $tls."
  else
    run openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=$name" \
      -addext "subjectAltName=DNS:$name,DNS:$name.local,DNS:localhost" \
      -keyout "$key" -out "$certificate"
    run chmod 600 "$key"
  fi
  run env CUBO_CONFIG_DIR="$(config_dir)" "$VENV/bin/python" - "$certificate" "$key" <<'PYTHON'
import sys

from cubo.config import CONFIG_FILE_NAME, Config, default_config_dir, load_config, save_config

certificate, key = sys.argv[1:3]
path = default_config_dir() / CONFIG_FILE_NAME
data = load_config(path).model_dump()
data["panel"].update(listen="network", ssl_certfile=certificate, ssl_keyfile=key)
save_config(Config.model_validate(data), path)
PYTHON
}

install_unit() {
  say "Serviço do systemd"
  local target
  target="$(unit_dir)/$UNIT_NAME"
  run mkdir -p "$(unit_dir)"
  if ((SIMULATE)); then
    note "[simular] gravar $target"
  else
    render_unit >"$target"
  fi
  # Sem o linger, o serviço do usuário só sobe depois que alguém entra na sessão.
  run sudo loginctl enable-linger "$USER"
  run systemctl --user daemon-reload
  run systemctl --user enable "$UNIT_NAME"
  run systemctl --user restart "$UNIT_NAME"
}

report() {
  local since="$1" deadline=$((SECONDS + WAIT_SECONDS))
  say "Pronto"
  if ((SIMULATE)); then
    note "[simular] aqui aparecem o endereço do painel e o código do primeiro acesso."
    return 0
  fi
  until journalctl --user -u "$UNIT_NAME" --since "$since" -o cat --no-pager 2>/dev/null | grep -q '^Painel:'; do
    systemctl --user is-active --quiet "$UNIT_NAME" ||
      fail "o Cubô não subiu. Veja o motivo com: journalctl --user -u cubo -n 50"
    ((SECONDS < deadline)) ||
      fail "o Cubô demorou mais de $WAIT_SECONDS s para subir. Acompanhe com: journalctl --user -u cubo -f"
    sleep 2
  done
  journalctl --user -u "$UNIT_NAME" --since "$since" -o cat --no-pager | grep -E '^(Painel|Primeiro acesso|Aviso)' || true
  if ((WITH_AVAHI)); then note "Na rede, também em: $(hostname).local"; fi
  note "Abra o painel, informe o código de primeiro acesso e defina a senha."
  note "Depois, em IA, escolha o provedor e cole a chave."
  note "Log: journalctl --user -u cubo -f  |  Parar: systemctl --user stop cubo"
}

main() {
  parse_args "$@"
  if ((SHOW_UNIT)); then
    render_unit
    exit 0
  fi
  require_normal_user
  check_system
  use_user_session
  local started
  started="$(date '+%Y-%m-%d %H:%M:%S')"
  install_packages
  install_app
  set_hostname
  enable_network
  install_unit
  report "$started"
}

main "$@"
