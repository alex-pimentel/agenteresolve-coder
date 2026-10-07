# Local runner harness

Runs `runner/runner.py` (stdlib-only) in a throwaway container built from
`runner/Dockerfile.local` (python:3.12-slim + git), without the full coder image
or opencode.

> **Note:** `RUNNER_AGENT_CMD` / `run_agent()` is **not yet invoked** by
> `implement()` — `implement()` currently uses the LLM path (`llm_chat`) only.
> Wiring the stub agent into `/implement` arrives in a later task, so this
> harness today only exercises boot + `/ping`.

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
- `stub_agent.sh` — fake coding agent: writes `src/generated.txt` and exits 0
  (not yet called by `implement()`, see note above).

## Mounts, paths and environment

- `./runner:/opt/runner:ro` — runner code, read-only.
- `./runner/tests/remotes:/remotes` — after `seed_repo.sh`, the bare remote is
  reachable inside the container at **`/remotes/demo.git`**.
- `runner_workspace:/workspace` — writable clone workspace
  (`WORKSPACE_DIR=/workspace`).
- `RUNNER_HOST=0.0.0.0` lets the port be reached from the host (the coder image
  binds loopback by default and is fronted by Caddy);
  `RUNNER_TOKEN=local-token`, `RUNNER_PORT=8090`, `RUNNER_SKIP_PUSH=1` and
  `RUNNER_GATE=0` keep the harness fully local. Note `RUNNER_SKIP_PUSH` and
  `RUNNER_GATE` are not yet read by `runner.py`.
