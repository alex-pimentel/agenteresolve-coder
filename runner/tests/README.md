# Local runner harness

Runs `runner/runner.py` (stdlib-only) in a throwaway container built from
`runner/Dockerfile.local` (python:3.12-slim + git), without the full coder image
or opencode.

> **Note:** `RUNNER_AGENT_CMD` / `run_agent()` **is** invoked by `implement()`
> when `RUNNER_AGENT_MODE=opencode` (the default mode): the runner runs the
> configured command (the stub locally, `opencode run` in the real image) in the
> cloned repo, then commits/pushes/opens the PR. The LLM path (`llm_chat`) is
> only used when `RUNNER_AGENT_MODE=llm`.

## Run

From `coder/`:

```bash
# 1. Seed the bare remote mounted at /remotes inside the container.
./runner/tests/seed_repo.sh

# 2. Boot the runner (builds the image).
docker compose -f docker-compose.local.yml up -d --build
curl -s http://localhost:8090/ping
# {"ok": true, "service": "agenteresolve-runner"}
```

Tear down (also drops the workspace volume):

```bash
docker compose -f docker-compose.local.yml down -v
```

## Layout

- `seed_repo.sh` — creates a **bare** remote plus a work repo seeded with one
  commit on `main`, then pushes `main` into the bare remote. Default root is
  `./runner/tests/remotes` (run from `coder/`); pass a different root as `$1`.
  It creates `<root>/demo.git` and `<root>/work`, and prints the absolute root.
  Seeded output is git-ignored.
- `stub_agent.sh` — fake coding agent: writes `src/generated.txt` and exits 0.
  Set `RUNNER_AGENT_CMD` to its path to drive `/implement` without opencode.

## Mounts, paths and environment

- `./runner:/opt/runner:ro` — runner code, read-only.
- `./runner/tests/remotes:/remotes` — after `seed_repo.sh`, the bare remote is
  reachable inside the container at **`/remotes/demo.git`**.
- `runner_workspace:/workspace` — writable clone workspace
  (`WORKSPACE_DIR=/workspace`).
- `RUNNER_HOST=0.0.0.0` lets the port be reached from the host (the coder image
  binds loopback by default and is fronted by Caddy);
  `RUNNER_TOKEN=local-token`, `RUNNER_PORT=8090`, `RUNNER_SKIP_PUSH=1` and
  `RUNNER_GATE=0` keep the harness fully local.

## Environment variables honored by `runner.py`

- `RUNNER_AGENT_MODE` — `opencode` (default) runs `RUNNER_AGENT_CMD` / `opencode run`; `llm` uses the orchestrator's LLM config.
- `RUNNER_AGENT_CMD` — agent command executed in the cloned repo (stub locally; empty in the real image so `opencode run` is used).
- `RUNNER_SKIP_PUSH=1` — commit locally but skip `git push` and PR creation.
- `RUNNER_GATE=1` — run the quality gate after the agent and retry up to `RUNNER_MAX_ITERATIONS`; `RUNNER_GATE_CMD` overrides gate auto-detection (blank/whitespace is treated as unset).
- `RUNNER_MAX_ITERATIONS`, `RUNNER_AGENT_TIMEOUT`, `WORKSPACE_DIR`, `OPENCODE_MODEL` — iteration cap, agent timeout, clone root, and default model.
