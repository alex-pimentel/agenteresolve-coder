# agenteresolve-coder

Serviço privado que roda o [opencode](https://opencode.ai/docs/web/) em modo web
(interface de browser) dentro de um container, atrás de **HTTP basic auth**
embutido do próprio opencode.

- **URL:** `https://coder.agenteresolve.com.br`
- **Login:** usuário `opencode` + `OPENCODE_SERVER_PASSWORD`
- **Imagem base:** `ghcr.io/anomalyco/opencode` (pinada em `ARG OPENCODE_VERSION`)
- **Provider:** OpenRouter (`OPENROUTER_API_KEY`), modelo padrão `openrouter/openai/gpt-4o-mini`

## O que esta imagem adiciona à oficial

- `git`, `openssh-client`, `curl`, `bash`
- usuário non-root `opencode` (UID 1000)
- auto-update desligado (`/etc/opencode/opencode.json`, tier gerenciado)
- `entrypoint.sh` que clona os 24 repos Agenteresolve em `/workspace` (shallow,
  em background, idempotente) e sobe `opencode web --hostname 0.0.0.0 --port 4096`

## Volumes persistentes (montados pelo Coolify)

| Caminho | Conteúdo |
| --- | --- |
| `/home/opencode` | credenciais (`auth.json`), sessões, config, cache |
| `/workspace` | os repos clonados |

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `OPENCODE_SERVER_PASSWORD` | — | **obrigatória**; basic auth do servidor |
| `OPENCODE_SERVER_USERNAME` | `opencode` | usuário do basic auth |
| `OPENROUTER_API_KEY` | — | chave do provider OpenRouter |
| `OPENCODE_MODEL` | (config do repo) | modelo padrão, ex.: `openrouter/openai/gpt-4o-mini` |
| `GITHUB_TOKEN` | — | token para clonar repos **privados** (escopo `repo`); sem ele só os públicos |
| `CLONE_REPOS` | lista dos 24 | repos a clonar (vírgula/espaço) |
| `GITHUB_ORG` | `alex-pimentel` | org dos repos |
| `CLONE_DEPTH` | `1` | profundidade do clone |
| `CLONE_ON_START` | `1` | `0` desliga o clone no boot |

## Rodar localmente

```bash
docker build -t agenteresolve-coder .
docker run --rm -p 4096:4096 \
  -e OPENCODE_SERVER_PASSWORD=secret \
  -e OPENROUTER_API_KEY=sk-or-... \
  -v coder-home:/home/opencode \
  -v coder-workspace:/workspace \
  agenteresolve-coder
# http://localhost:4096 (login: opencode / secret)
```

## Deploy

Gerenciado por `deploy-coder.sh` na raiz do projeto Agenteresolve (Coolify +
DNS Cloudflare). Não contém segredos.
