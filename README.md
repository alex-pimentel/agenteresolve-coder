# agenteresolve-coder

Serviço privado que roda, **no mesmo container**, dois ambientes de
desenvolvimento acessíveis pelo browser:

- **opencode web** — interface do [opencode](https://opencode.ai/docs/web/), com
  HTTP basic auth embutido.
- **VS Code Web** ([code-server](https://github.com/coder/code-server)) — VS Code
  no navegador, com login por senha.

Um **Caddy interno** (porta única exposta ao Traefik) roteia por `Host`:

| URL | Backend | Auth |
| --- | --- | --- |
| `https://coder.agenteresolve.com.br` | opencode web (`127.0.0.1:4096`) | basic auth (`opencode` + `OPENCODE_SERVER_PASSWORD`) |
| `https://code.agenteresolve.com.br` | code-server (`127.0.0.1:8081`) | senha (`OPENCODE_SERVER_PASSWORD`) |

- **Imagem base:** `codercom/code-server` (Debian — code-server exige glibc) + opencode pinado.
- **Provider:** OpenRouter (`OPENROUTER_API_KEY`), modelo padrão `openrouter/openai/gpt-4o-mini`.
- **Processos** (supervisionados pelo `supervisor`): `caddy`, `opencode`, `code-server`.

## Por que Caddy?

O Coolify não mapeia 2 portas por domínio em *standard application*
(`domain_port_overrides` fica vazio). Então expomos **uma** porta (8080 = Caddy) e
o Caddy distribui por `Host` para os dois backends em loopback. O TLS é terminado
no Traefik.

## Detalhes de operação

- O code-server usa uma config fixa em `/etc/code-server/config.yaml`
  (`bind-addr: 127.0.0.1:8081`) e tem `PORT=8081` fixado no supervisor — o Coolify
  injeta `PORT` (de `ports_exposes`) e o code-server o usaria como bind, colidindo.
- `entrypoint.sh` inicia em `~/agenteresolve` (o projeto) e dispara o clone dos 24
  repos em `$HOME/agenteresolve/<repo>` (shallow, em background, idempotente).
- auto-update do opencode desligado (`/etc/opencode/opencode.json`, tier gerenciado).

## Volume persistente (montado pelo Coolify)

| Caminho | Conteúdo |
| --- | --- |
| `/home/opencode` | credenciais, sessões, config, cache, dados do code-server |
| `/home/opencode/agenteresolve` | **o projeto**: os 24 repos clonados (`<repo>/`) |

> Os repos ficam sob o `$HOME` (em `~/agenteresolve`) de propósito: o diálogo
> **"Abrir projeto"** do opencode web só lista diretórios sob o home. O opencode
> inicia com `cwd` em `~/agenteresolve`, então esse é o projeto ativo — todos os
> repos ficam acessíveis ao mesmo tempo.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `OPENCODE_SERVER_PASSWORD` | — | **obrigatória**; senha do opencode **e** do code-server |
| `OPENCODE_SERVER_USERNAME` | `opencode` | usuário do basic auth do opencode |
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
docker run --rm -p 8080:8080 \
  -e OPENCODE_SERVER_PASSWORD=secret \
  -e OPENROUTER_API_KEY=sk-or-... \
  -v coder-home:/home/opencode \
  agenteresolve-coder
# opencode:     http://localhost:8080 (Host: coder.agenteresolve.com.br)
# VS Code Web:  http://localhost:8080 (Host: code.agenteresolve.com.br)
# dica: curl -H 'Host: code.agenteresolve.com.br' http://localhost:8080/login
```

## Deploy

Gerenciado por `deploy-coder.sh` na raiz do projeto Agenteresolve (Coolify +
DNS Cloudflare). Não contém segredos.
