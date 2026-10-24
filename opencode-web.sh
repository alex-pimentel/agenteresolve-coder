#!/bin/sh
# opencode-web.sh — inicia o servidor web do opencode atrás do Caddy (:4096).
#
# Por que este wrapper existe: o binário pinado na imagem (V1) usa
# `opencode web`, enquanto o opencode V2 expõe o mesmo servidor como
# `opencode serve`. Além disso, o config global vive no volume persistente
# (`$HOME/.config/opencode/opencode.json`) e pode estar no schema V2
# (`permissions`), que o V1 recusa com "Configuration is invalid". O wrapper
# escolhe o binário e o subcomando certos para o container não ficar em loop
# de restart após um upgrade feito dentro do volume.
set -eu

HOST="${OPENCODE_HOST:-127.0.0.1}"
PORT="${OPENCODE_PORT:-4096}"

# V2: instalado no home persistente (installer/`opencode upgrade`).
V2_BIN="${OPENCODE_V2_BIN:-$HOME/.opencode/bin/opencode}"
# V1: pinado na imagem pelo Dockerfile.
V1_BIN="${OPENCODE_V1_BIN:-/usr/local/bin/opencode}"

CONFIG="${OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"

# `permissions` (plural) só existe no schema V2; `permission` (singular) é V1.
config_needs_v2() {
    [ -f "$CONFIG" ] && grep -q '"permissions"' "$CONFIG"
}

if [ -x "$V2_BIN" ]; then
    echo "opencode-web: using V2 binary $V2_BIN (serve) on $HOST:$PORT" >&2
    exec "$V2_BIN" serve --hostname "$HOST" --port "$PORT"
fi

if config_needs_v2; then
    echo "opencode-web: $CONFIG uses the V2 schema (permissions) but no V2" >&2
    echo "opencode-web: binary was found at $V2_BIN; refusing to start V1." >&2
    exit 78
fi

echo "opencode-web: using V1 binary $V1_BIN (web) on $HOST:$PORT" >&2
exec "$V1_BIN" web --hostname "$HOST" --port "$PORT"
