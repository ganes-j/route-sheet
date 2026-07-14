# CLAUDE.md router section (template)

Insert everything between the START/END markers into your always-loaded agent instructions file (`~/.claude/CLAUDE.md` for Claude Code). The markers make the block surgically removable — revert by deleting the marked block. SETUP.md inserts and verifies this for you.

---

```markdown
<!-- MODEL ROUTER START (revert: delete this whole marked block) -->
# Model Router

Route each unit of multi-unit work to the executor best suited for it — Codex, a local model, a cheap Claude tier, or the coordinator (you) — instead of doing everything in the main loop. Policy + constraints: `~/.claude/ROUTING_POLICY.md`. Local-model inventory + `llocal` usage: `~/.claude/LOCAL_MODELS.md`.

**Kill switch:** if `~/.claude/.router-off` exists, the router is OFF — work inline, no routing or delegation. Soft-disable anytime: `touch ~/.claude/.router-off` (the SessionStart hook injects the active/disabled state).

**At plan time (`/ce-plan`):** consult `ROUTING_POLICY.md`, then run the **route-plan** skill to write a sidecar manifest (`<plan-basename>-routing.md`) assigning each U-ID an executor. Approved with the plan (gated mode). Never embed executor tags in the plan body.

**At execution (`/ce-work`):** check for a sibling `<plan-basename>-routing.md` and dispatch each unit to its assigned executor:
- **codex-implementer / codex-scout** → the **codex-dispatch** skill (pre-flight guards + mandatory orchestrator re-check; Codex output is more untrusted than a Claude subagent — read the diff and re-run the load-bearing check yourself).
- **llocal** (bulk text/JSON extraction, PII-bound batch, vision/OCR) → `~/.claude/bin/llocal` `run`/`batch` (never raw `ollama run`; pick the model from `LOCAL_MODELS.md`; offload mechanical/bulk work only, keep judgment yourself, verify every item).
- **coordinator** → do it yourself: architecture, API design, spec-writing-as-the-work, tiny edits (<~20 lines), session-tool/secret/browser/MCP work, destructive ops, GitHub mutations, the verification gate (the never-delegate set).
- Dispatch is **default-binding**: running a manifest-assigned unit inline without a logged override is a verification-gate miss. Log deviations with rationale to the manifest execution log + `ROUTING_POLICY.md` §5.
- **Outcome line = done-condition (every executor).** A routed unit is not done until its outcome line exists — in the plan's manifest execution log (ad-hoc work → `~/.claude/router-adhoc-outcomes.md`), written in the `ROUTING_POLICY.md` §6 canonical grammar. `codex-dispatch` writes its own; for **llocal and Claude-worker units the coordinator writes the line after re-checking the output**. No line, no learning — this is the flywheel's only input.
- **Fallback ladder:** no manifest, or a unit's U-ID isn't in it (plan was deepened) → work that unit inline, note the gap, offer a `route-plan` run. Never improvise routing.

**Ad-hoc (non-plan) work:** for batch extraction or PII-bound bulk jobs that never enter `/ce-plan`, consult the constraint layer and dispatch to `llocal` directly — this is llocal's core use.

**Hard constraints (always win — `ROUTING_POLICY.md` §1):** PII-bound work never goes to Codex; on a live prod credential, Codex is scrubbed into an isolated worktree (a fresh worktree omits the gitignored `.env`) and re-scanned rather than skipped — hard-skip only for a deny-listed dir or a still-dirty re-scan; dev-grade `.env` (localhost + dev keys) dispatches directly, worktree-free; `codex cloud exec` needs explicit per-unit approval; Lane A (`ce-work-beta delegate:codex`) is typed-argument-only and `work_delegate: codex` is never persisted in a repo config.

**Flywheel (R0-gated):** at `/ce-compound`, invoke the **router-flywheel** skill to read routing-manifest outcome lines + the `ROUTING_POLICY.md` §5 drift log and propose task-shape cell updates. It self-gates on **R0**: until 3 consecutive real `/ce-plan` runs have emitted manifests unprompted (status in `~/.claude/ROUTER_STATUS.md`), it runs **dry-run** — reports what it would propose, writes nothing. Once R0 passes, count/date increments apply silently; every state change (`❓→✅`, `✅→❌`, new row) still needs the user's sign-off.
<!-- MODEL ROUTER END -->
```
