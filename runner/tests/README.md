# Local runner harness

Runs `runner/runner.py` (stdlib-only) in a throwaway `python:3.12-slim`
container, without the full coder image or opencode. The agent is replaced by
`stub_agent.sh`, so `/implement` commits the stub's file instead of invoking a
real coding agent.

## Run

From `coder/`:

```bash
docker compose -f docker-compose.local.yml up -d --build
curl -s http://localhost:8090/ping
# {"ok": true, "service": "agenteresolve-runner"}
```

Tear down (also drops the workspace volume):

```bash
docker compose -f docker-compose.local.yml down -v
```

## Layout

- `seed_repo.sh` — creates a bare remote (`remotes/demo.git`) plus a work repo
  with one commit on `main`. Prints the root path. Usage: `./seed_repo.sh [root]`.
- `stub_agent.sh` — fake coding agent: writes `src/generated.txt` and exits 0.

## Environment

The compose file sets `RUNNER_HOST=0.0.0.0` so the port is reachable from the
host (the coder image binds loopback by default and is fronted by Caddy).
`RUNNER_TOKEN=local-token`, `RUNNER_SKIP_PUSH=1` and a mounted bare remote at
`/remotes/demo.git` keep the harness fully local.
