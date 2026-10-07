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
