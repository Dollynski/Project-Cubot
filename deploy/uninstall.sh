#!/usr/bin/env bash
# Remove o serviço do Cubô. Não desinstala pacotes do sistema nem apaga a pasta do projeto.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="cubo.service"

# shellcheck source=deploy/common.sh
source "$SCRIPT_DIR/common.sh"

DELETE_DATA=0

usage() {
  cat <<'TEXTO'
Uso: deploy/uninstall.sh [opções]

Para o Cubô e remove a unidade do systemd.

Opções:
  --apagar-dados  apaga também a configuração, as chaves e os modelos (pede confirmação)
  --sim           não pergunta nada, responde sim
  --simular       só mostra o que faria, sem mudar nada
  -h, --ajuda     mostra esta ajuda
TEXTO
}

parse_args() {
  while (($#)); do
    case "$1" in
      --apagar-dados) DELETE_DATA=1 ;;
      --sim) ASSUME_YES=1 ;;
      --simular) SIMULATE=1 ;;
      -h | --ajuda)
        usage
        exit 0
        ;;
      *) usage_error "opção desconhecida: $1" ;;
    esac
    shift
  done
}

remove_service() {
  say "Serviço do systemd"
  local target
  target="$(unit_dir)/$UNIT_NAME"
  run systemctl --user disable --now "$UNIT_NAME" || note "O serviço não estava ligado."
  run rm -f "$target"
  run systemctl --user daemon-reload
}

remove_data() {
  ((DELETE_DATA)) || return 0
  say "Dados"
  local config data
  config="$(config_dir)"
  data="$(data_dir)"
  if confirm "Apagar $config (configuração e chaves) e $data (modelos)? Isso não pode ser desfeito."; then
    run rm -rf "$config" "$data"
  else
    note "Nada foi apagado."
  fi
}

main() {
  parse_args "$@"
  require_normal_user
  use_user_session
  remove_service
  remove_data
  say "Pronto"
  note "Ficaram o projeto, o .venv e os pacotes do sistema. Para desligar o linger: sudo loginctl disable-linger \"\$USER\""
}

main "$@"
