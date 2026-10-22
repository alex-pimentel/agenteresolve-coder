# opencode headless spike

Manual spike closing Phase 0 / Task 0.2 of the
`2026-10-07-opencode-agent-workflow` plan. Records how the coding runner drives
the real `opencode` binary and what the real end-to-end run produced.

## Environment

| Item | Value |
| --- | --- |
| opencode version | `1.18.34` |
| Mechanism | CLI headless: `opencode run --auto --model <id> "<prompt>"` |
| Chosen model id | `opencode/deepseek-v4.1-flash` |
| Provider key env var | `OPENCODE_API_KEY` (set only inside the runner process by `agent_env_and_model`) |
| Runner agent mode | `RUNNER_AGENT_MODE=opencode`, `RUNNER_AGENT_CMD` empty so `opencode run` is used |

The runner invokes opencode through `run_agent()` with a process group and a
timeout; the environment passed to the agent is a **whitelist** of safe vars
(`PATH`, `HOME`, `LANG`, …) plus the provider key — never the runner's
`RUNNER_TOKEN` or `GITHUB_TOKEN`.

## Real E2E result

Two runs were performed against a real coder image with a real
`OPENCODE_API_KEY` (boot → clone → branch → real `opencode run` → commit →
board column). No secret values are recorded here.

1. **Default paid model — blocked by billing (external).**
   `opencode/deepseek-v4.1-flash` is rejected by the opencode gateway because
   the provided key's Zen workspace has **no payment method**:

   ```
   > build · deepseek-v4.1-flash
   Error: No payment method. Add a payment method here:
   https://opencode.ai/workspace/<redacted>/billing
   RC=1
   ```

   The orchestrator reports `Implementação falhou` and the card stays in
   `A Fazer`. This is an account/billing issue, not a runner defect; the
   same key and binary work for entitled/free models.

2. **Entitled/free model — full pipeline green.**
   Using an entitled model the complete flow succeeds:

   ```
   $ OPENCODE_E2E_MODEL=<entitled-model> bash scripts/local-opencode-e2e.sh
   ==> configuring LLM model for the orchestrator
   ==> seeding board + card
   card id: <n>
   ==> running orchestrator (real agent; may take a few minutes)
   Card <n>: Implementado; movido para Pull Request.
   ==> asserting column
   column: Pull Request
   ==> asserting runner branch + commit
   branch: feature/card-<n>
   <sha> feature(card-<n>): E2E local: gerar arquivo
    src/generated.txt | 1 +
   E2E (opencode) OK
   ```

   Card moved to **Pull Request**, branch created, commit made and the agent's
   file (`src/generated.txt`) created — the full pipeline works end to end.

## Conclusion

The headless CLI mechanism is confirmed working at `1.18.34`. The only blocker
to a green run with the as-chosen model is external billing on the key's Zen
workspace; as soon as that workspace can access `opencode/deepseek-v4.1-flash`,
the E2E passes unchanged. Detail and reproduction commands (secret-safe) are in
`website/.superpowers/sdd/2026-10-07-opencode-agent-workflow/task-5.2-report.md`.

## Update 2026-10-17 — credential invalid, free models are anonymous-only

Probed again from the same runner image/key (`sk-…`, 67 chars, unchanged since
2026-10-07 in `.env.deploy`):

- **Every** `opencode/` model — free or paid, including `big-pickle` and
  `deepseek-v4.1-flash-free` — now fails with
  `Upstream request failed: Invalid credential` when **any** key is passed
  (control test with a deliberately bogus key shows the identical error).
- Without any credential (`env -u OPENCODE_API_KEY`), the **free** models run
  fine: `opencode/big-pickle`, `opencode/deepseek-v4.1-flash-free`,
  `opencode/glm-5.3-flash-free` all answered. The paid
  `opencode/deepseek-v4.1-flash` without a key returns a generic server error
  (illustrative, not usable).

Conclusion: the API key in `.env.deploy` was invalidated server-side (expired
or revoked in the opencode Zen workspace), and opencode free models work
anonymously. Conclusions applied in code:

- Default model moved to `opencode/deepseek-v4.1-flash-free` (free variant of
  the user-chosen model, no billing involved) in `scripts/local-opencode-e2e.sh`
  and `docker-compose.local.opencode.yml`.
- `scripts/local-opencode-e2e.sh` **unsets `OPENCODE_API_KEY` by default** (the
  key in `.env.deploy` is stale and poisons every `opencode/` call). Use
  `OPENCODE_E2E_USE_KEY=1 OPENCODE_API_KEY=<valid>` only to exercise paid models.
- Production note: a stale key must not be shipped into the agent env; keep the
  coder app keyless while using free models, or rotate the key at
  `https://opencode.ai/workspace/<workspace>/keys` before switching to paid ids.

