# agenteresolve-coder — opencode web privado, sobre a imagem oficial.
#
# Base: ghcr.io/anomalyco/opencode (Alpine + binário + ripgrep, root, sem git,
# autoupdate ligado). Esta camada adiciona o que falta para rodar como serviço:
#   - git / openssh / curl / bash
#   - usuário non-root `opencode` (UID 1000)
#   - auto-update desligado (managed config /etc/opencode, tier mais alto)
#   - entrypoint que clona os repos no volume e sobe `opencode web`
#
# Build:  docker build -t agenteresolve-coder .
# Pin:    docker build --build-arg OPENCODE_VERSION=1.18.34 .
ARG OPENCODE_VERSION=1.18.34
FROM ghcr.io/anomalyco/opencode:${OPENCODE_VERSION}

ARG UID=1000
ARG GID=1000

RUN apk add --no-cache \
    bash \
    ca-certificates \
    curl \
    git \
    openssh-client

RUN addgroup -g "$GID" opencode \
    && adduser -D -u "$UID" -G opencode -s /bin/bash opencode \
    && mkdir -p /home/opencode/.config/opencode \
    && chown -R opencode:opencode /home/opencode

# Config default (tier global): modelo padrão no OpenRouter. Sobrescrevível pelo
# OPENCODE_MODEL via env (vira OPENCODE_CONFIG_CONTENT no entrypoint).
COPY opencode.json /home/opencode/.config/opencode/opencode.json
# Managed config (tier mais alto): desliga o auto-update dentro do container.
COPY opencode.managed.json /etc/opencode/opencode.json

COPY entrypoint.sh init-clone.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/init-clone.sh \
    # `opencode web` tenta abrir um browser via xdg-open; no-op evita stack trace.
    && printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/xdg-open \
    && chmod 755 /usr/local/bin/xdg-open \
    && chown -R opencode:opencode /home/opencode

USER opencode
ENV HOME=/home/opencode
# HOME é o diretório de trabalho: o diálogo "Abrir projeto" do opencode web só
# navega dentro do $HOME, então os repos precisam ficar aqui (não em /workspace).
WORKDIR /home/opencode

EXPOSE 4096

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS -u "${OPENCODE_SERVER_USERNAME:-opencode}:${OPENCODE_SERVER_PASSWORD}" http://127.0.0.1:4096/global/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["opencode", "web", "--hostname", "0.0.0.0", "--port", "4096"]
