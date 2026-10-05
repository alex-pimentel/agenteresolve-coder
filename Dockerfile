ARG CODE_SERVER_VERSION=4.140.0
FROM codercom/code-server:${CODE_SERVER_VERSION}
USER root
RUN echo "probe: apt-get" \
 && apt-get update \
 && apt-get install -y --no-install-recommends supervisor \
 && rm -rf /var/lib/apt/lists/* \
 && which supervisord \
 && echo "probe: apt OK"
