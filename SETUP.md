# SETUP.md — agent-executable install

> **Status: skeleton.** This runbook is written for an agent (e.g. Claude Code) to execute on a user's behalf. Structure below is the contract; steps are being filled in.

## Adoption tiers

- **Tier 0 — read-only.** Nothing installed. Use `docs/` to learn the pattern.
- **Tier 1 — policy + manifests.** Routing policy, route-plan skill, kill switch. Coordinator-only execution; no Codex, no local models.
- **Tier 2 — + Codex lane.** Adds codex-dispatch with the constraint layer and worktree scrub.
- **Tier 3 — + local-model lane.** Adds `llocal` + Ollama.

## Runbook shape (every tier)

1. **Preflight** — capability probes with expected outputs.
2. **Consent gate** — exact list of writes before any write.
3. **Apply** — idempotent, marker-bounded, append-only.
4. **Verify** — per-step checks + the sample-plan smoke test in `fixtures/`.
5. **Degrade honestly** — report the tier reached and exactly what is unavailable.
