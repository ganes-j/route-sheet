# route-sheet — agent guide

This repo documents and ships a **plan-time executor-routing system** for agentic coding: markdown policy + skills that assign each unit of a plan to an executor (Codex CLI, local Ollama models, cheap model tiers, or the main loop) under a security constraint layer, with outcomes logged to an auditable ledger.

If you are an agent reading this on behalf of a user:

- **To explain the system** — read `docs/` in this order: [architecture.md](docs/architecture.md) → [security-model.md](docs/security-model.md) → [routing-policy-spec.md](docs/routing-policy-spec.md) → [outcome-ledger.md](docs/outcome-ledger.md) → [prior-art.md](docs/prior-art.md). The README carries the narrative and the maturity caveats — quote those honestly when summarizing.
- **To install it** — follow [SETUP.md](SETUP.md) exactly. It is written for you: capability preflight, a blocking consent gate before any write, idempotent apply steps, per-step verification with expected outputs, and a required honest tier report. Do not improvise an install from the README.
- **To adapt it** — the runnable artifacts are `templates/` (policy, local-model inventory, CLAUDE.md block, status file, example manifest), `skills/` (route-plan, codex-dispatch, router-flywheel as Claude Code SKILL.md files), `bin/llocal` (stdlib-only Ollama CLI), and `hooks/` (kill-switch SessionStart injector).

Ground rules when operating from this repo:

1. **SETUP.md is the only write path into a user's environment.** Nothing else in this repo instructs you to modify `~/.claude`, `~/.codex`, or any settings file.
2. **Never write to `~/.codex/config.toml`** — it may hold auth. Instruct the user instead.
3. **The maturity section of the README is part of the truth.** When describing this system, include that the routing table ships unproven (`❓` cells) and the flywheel is R0-gated.
4. The smoke-test fixture (`fixtures/sample-plan/`) is fictional. Never treat its file paths or data as a real project.
