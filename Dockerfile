# agenteresolve-coder — opencode web + VS Code Web (code-server) no MESMO container.
#
# Base Debian: o code-server exige glibc (não roda em Alpine/musl). A imagem
# oficial `codercom/code-server` já traz git/curl/dumb-init e o usuário UID 1000.
# Dois processos são supervisionados pelo `supervisor`:
#   - opencode web      -> 0.0.0.0:4096  (basic auth via OPENCODE_SERVER_PASSWORD)
#   - code-server (VS Code Web) -> 0.0.0.0:8080 (senha via PASSWORD)
#
# Build:  docker build -t agenteresolve-coder .
# Pin:    docker build --build-arg CODE_SERVER_VERSION=4.140.0 --build-arg OPENCODE_VERSION=1.18.34 .
ARG CODE_SERVER_VERSION=4.140.0
ARG OPENCODE_VERSION=1.18.34
FROM codercom/code-server:${CODE_SERVER_VERSION}

# ARGs globais só valem no FROM; redeclarar para usar no RUN.
ARG OPENCODE_VERSION

USER root

# `supervisor` gerencia os dois processos. git/curl/openssh-client/dumb-init já
# vêm na imagem base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends supervisor \
    && rm -rf /var/lib/apt/lists/*

# opencode (binário glibc) instalado no build. O Coolify builda na própria VPS,
# então a detecção de CPU (AVX2/baseline) do instalador coincide com a runtime.
RUN mkdir -p /tmp/ocinstall \
    && export HOME=/tmp/ocinstall \
    && curl -fsSL https://opencode.ai/install \
        | bash -s -- --version "${OPENCODE_VERSION}" --no-modify-path \
    && mv /tmp/ocinstall/.opencode/bin/opencode /usr/local/bin/opencode \
    && chmod 755 /usr/local/bin/opencode \
    && rm -rf /tmp/ocinstall \
    && opencode --version

# Config default do opencode (tier global). O modelo padrão também pode vir do
# OPENCODE_MODEL (vira OPENCODE_CONFIG_CONTENT no entrypoint).
COPY opencode.json /home/opencode/.config/opencode/opencode.json
# Managed config (tier mais alto): desliga o auto-update dentro do container.
COPY opencode.managed.json /etc/opencode/opencode.json

COPY supervisord.conf /etc/supervisor/supervisord.conf
COPY entrypoint.sh init-clone.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/init-clone.sh \
    && mkdir -p /home/opencode/.config/opencode /home/opencode/agenteresolve \
    && chown -R 1000:1000 /home/opencode

# Usuário não-root da imagem (coder, UID 1000) — casa com o dono do volume.
USER 1000
ENV HOME=/home/opencode
WORKDIR /home/opencode/agenteresolve

EXPOSE 4096 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS -u "${OPENCODE_SERVER_USERNAME:-opencode}:${OPENCODE_SERVER_PASSWORD}" http://127.0.0.1:4096/global/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]
