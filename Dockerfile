ARG CODE_SERVER_VERSION=4.140.0
FROM codercom/code-server:${CODE_SERVER_VERSION}
USER root
RUN echo "probe: baixando asset do GitHub" \
 && curl -fsSL -o /tmp/oc.tar.gz https://github.com/anomalyco/opencode/releases/download/v1.18.34/opencode-linux-x64.tar.gz \
 && ls -la /tmp/oc.tar.gz \
 && echo "probe: asset OK"
