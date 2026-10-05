#!/bin/bash
# Entrypoint: prepara o workspace (clone em background), aplica overrides de
# config via env e executa o comando (por padrão, `opencode web`).
set -euo pipefail

HOME_DIR="${HOME:-/home/opencode}"
PROJECT_DIR="$HOME_DIR/agenteresolve"

# O opencode usa o cwd como projeto. Iniciamos dentro de ~/agenteresolve, que
# contém todos os repos, para trabalhar com todos ao mesmo tempo.
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Clona/move os repos em background (idempotente), para o servidor subir já.
if [ "${CLONE_ON_START:-1}" = "1" ]; then
    /usr/local/bin/init-clone.sh >>"$HOME_DIR/.clone.log" 2>&1 &
fi

# Permite definir o modelo padrão pelo ambiente (ex.: openrouter/openai/gpt-4o-mini).
if [ -n "${OPENCODE_MODEL:-}" ]; then
    export OPENCODE_CONFIG_CONTENT="{\"model\":\"${OPENCODE_MODEL}\"}"
fi

# Salvaguarda: não subir servidor em todas as interfaces sem senha.
if [ "${1:-}" = "opencode" ] && { [ "${2:-}" = "web" ] || [ "${2:-}" = "serve" ]; } \
   && [[ " $* " == *" --hostname 0.0.0.0 "* ]] \
   && [ -z "${OPENCODE_SERVER_PASSWORD:-}" ]; then
    echo "agenteresolve-coder: recusando subir '$1 $2' em 0.0.0.0 sem OPENCODE_SERVER_PASSWORD" >&2
    exit 1
fi

exec "$@"
