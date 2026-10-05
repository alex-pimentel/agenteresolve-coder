# agenteresolve-coder — opencode web + VS Code Web (code-server) no MESMO container.
#
# Base Debian: o code-server exige glibc (não roda em Alpine/musl). A imagem
# oficial `codercom/code-server` já traz git/curl/dumb-init e o usuário UID 1000.
# Três processos supervisionados pelo `supervisor`:
#   - caddy       -> 0.0.0.0:8080  (proxy interno; única porta exposta ao Traefik)
#   - opencode web-> 127.0.0.1:4096 (basic auth via OPENCODE_SERVER_PASSWORD)
#   - code-server -> 127.0.0.1:8081 (senha via PASSWORD)
# O Caddy roteia por Host: coder.* -> opencode, code.* -> code-server. (Coolify
# não mapeia 2 portas por domínio em app padrão, por isso o proxy interno.)
#
# Build:  docker build -t agenteresolve-coder .
ARG CODE_SERVER_VERSION=4.140.0
ARG OPENCODE_VERSION=1.18.34
ARG CADDY_VERSION=2.11.7
FROM codercom/code-server:${CODE_SERVER_VERSION}

# ARGs globais só valem no FROM; redeclarar para usar no RUN.
ARG OPENCODE_VERSION
ARG CADDY_VERSION

USER root

# `supervisor` gerencia os processos. git/curl/openssh-client/dumb-init já vêm
# na imagem base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# Caddy (proxy interno), pinado.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in amd64) a=amd64 ;; arm64) a=arm64 ;; *) a=amd64 ;; esac; \
    curl -fsSL -o /tmp/caddy.tar.gz \
        "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_${a}.tar.gz"; \
    tar -xzf /tmp/caddy.tar.gz -C /tmp caddy; \
    mv /tmp/caddy /usr/local/bin/caddy; \
    chmod 755 /usr/local/bin/caddy; \
    rm -f /tmp/caddy.tar.gz; \
    caddy version

# opencode (binário glibc) baixado direto do release, pinado. Baixa o asset
# `-baseline` se a CPU não tiver AVX2 (o build roda na própria VPS).
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) a=x64 ;; \
        arm64) a=arm64 ;; \
        *) a=x64 ;; \
    esac; \
    if [ "$a" = "x64" ] && ! grep -qwi avx2 /proc/cpuinfo; then variant="-baseline"; else variant=""; fi; \
    curl -fsSL -o /tmp/oc.tar.gz \
        "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${a}${variant}.tar.gz"; \
    tar -xzf /tmp/oc.tar.gz -C /tmp; \
    mv /tmp/opencode /usr/local/bin/opencode; \
    chmod 755 /usr/local/bin/opencode; \
    rm -f /tmp/oc.tar.gz; \
    opencode --version

# Config default do opencode (tier global). O modelo padrão também pode vir do
# OPENCODE_MODEL (vira OPENCODE_CONFIG_CONTENT no entrypoint).
COPY opencode.json /home/opencode/.config/opencode/opencode.json
# Managed config (tier mais alto): desliga o auto-update dentro do container.
COPY opencode.managed.json /etc/opencode/opencode.json

COPY Caddyfile /etc/caddy/Caddyfile
COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh init-clone.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/init-clone.sh \
    && mkdir -p /home/opencode/.config/opencode /home/opencode/agenteresolve \
    && chown -R 1000:1000 /home/opencode

# Usuário não-root da imagem (coder, UID 1000) — casa com o dono do volume.
USER 1000
ENV HOME=/home/opencode
WORKDIR /home/opencode/agenteresolve

# Só o Caddy é exposto; ele distribui por Host para os backends em loopback.
EXPOSE 8080

ENTRYPOINT ["entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
