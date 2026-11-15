#!/usr/bin/env bash
# Funções usadas por install.sh e uninstall.sh. Não é para rodar sozinho.
# shellcheck disable=SC2034  # as variáveis abaixo são lidas pelos scripts que carregam este arquivo

SIMULATE=0
ASSUME_YES=0

say() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
fail() {
  printf 'Erro: %s\n' "$*" >&2
  exit 1
}

# Erro de uso (opção inválida): mostra o modo de usar e sai com código 2.
usage_error() {
  printf 'Erro: %s\n\n' "$*" >&2
  usage >&2
  exit 2
}

# Roda o comando, ou só mostra o que rodaria quando o script foi chamado com --simular.
run() {
  if ((SIMULATE)); then
    printf '    [simular] %s\n' "$*"
  else
    "$@"
  fi
}

# Pergunta sim ou não, e o padrão é não. Com --sim (ou --simular) responde sim sem perguntar.
confirm() {
  if ((ASSUME_YES || SIMULATE)); then
    return 0
  fi
  local answer
  read -r -p "$1 [s/N] " answer || return 1
  [[ "$answer" =~ ^[sSyY]$ ]]
}

config_dir() { printf '%s' "${CUBO_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/cubo}"; }
data_dir() { printf '%s' "${CUBO_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/cubo}"; }
unit_dir() { printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"; }

require_normal_user() {
  if ((EUID == 0)); then
    fail "rode como o seu usuário, sem sudo: o Cubô é um serviço do usuário. O script pede sudo só quando precisa."
  fi
}

# O systemctl --user precisa saber onde está a sessão do usuário (ex.: ao entrar por SSH).
use_user_session() {
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
}
