---
name: route-plan
description: Write a sidecar routing manifest for a plan — assign each implementation unit (U-ID) to the best-suited executor (codex-implementer, codex-scout, llocal, a Claude tier, or coordinator) per ~/.claude/ROUTING_POLICY.md. Use right after /ce-plan produces a plan, or when asked to route a plan's units. Produces <plan-basename>-routing.md next to the plan; never edits the plan body.
---

# Route Plan (sidecar manifest writer)

Records the plan-time routing judgment beside the plan so execution can dispatch deterministically. The plan body is never touched (ce-plan's portability rule; U-IDs are the stable join).

**Kill switch:** if `~/.claude/.router-off` exists, decline — write nothing, tell the user the router is off.

## Procedure

1. **Load the policy.** Read `~/.claude/ROUTING_POLICY.md`. Missing or malformed → decline with a message; never improvise routing without it.
2. **Read the plan, minting U-IDs if the source has none.**
   - **Headings present** (grep `^### U[0-9]` matches): extract every unit heading `### U<N>. <name>`, plus each unit's Goal, Files, Approach, and Verification. Standard path — no minting.
   - **No headings** (an ID-less TODO.md, GitHub issue-tasklist markdown, or a pasted plain-text plan): **mint stable U-IDs** before routing. Detect the items (markdown task-list lines `- [ ]` / `- `, numbered items, or one-item-per-paragraph pasted text) and assign each the next sequential `[U<N>]` marker. **Consent gate before writing:** state the exact file you will modify and the markers you will add, then wait for an explicit yes. On yes, write the `[U<N>]` markers back into the source so it becomes the stable ID home (re-runs re-read them — step 5). On decline, mint into a read-only derived copy for this run only and say so; the source is not modified. Then read each minted unit's goal/scope/verify as above.
   - Either branch feeds the shape match, the load-bearing check, and the discipline floor (step 3).
3. **Route each unit** — apply the policy in order:
   - **Constraint layer first** (`ROUTING_POLICY.md` §1): PII-bound → llocal/coordinator (never Codex); a **deny-listed** dispatch dir → not Codex; a unit whose dir holds a **host-detection** prod credential (non-deny-list) → `codex-implementer (worktree-scrub)` — do NOT pre-exclude to coordinator; codex-dispatch scrubs it into an isolated worktree at execution (§1.2), so pre-excluding here would mean the capability never runs; never-delegate shapes (architecture, spec-writing-as-the-work, tiny <~20-line edits, session-tool/secret/browser/MCP work, destructive ops, GitHub mutations, the verification gate) → coordinator.
   - **Then the task-shape table** (§2): match the unit to a shape (impl-from-frozen-spec, mechanical-refactor, bugfix-with-repro, CI/dep/test-bulk, batch-extraction, PII-batch, vision/OCR, huge-context-sweep, adversarial-review) → its preferred executor.
   - **Staleness check:** when you consult a cell to route a unit, compare its `last YYYY-MM-DD` to today. If **>90 days** old, emit ONE dismissible offer naming that cell — a scoped freshness-research pass before routing (e.g. a recent-community-signal search; never auto-run — external research costs time/credits). Declining proceeds with the cell unchanged. An accepted refresh may annotate the cell or add a `❓` row (§4) but **never flips it to `✅`** — only real outcomes do. The user approves material changes; date-stamp/evidence-only refreshes apply silently. (Dormant until a cell ages past 90 days.)
   - **Discipline floor (matters most for minted or thin units):** a unit is **full** only if it has an inferable goal/scope AND a load-bearing verify command; otherwise it is **bare**. A bare unit is **never** assigned to a write-worker (codex-implementer, llocal batch) — codex-dispatch's re-check (§4) would have no command to run against it — so it stays coordinator or a read-only executor. This is the same instinct as the coordinator-default below, made explicit: weak input yields a visibly hedged manifest, not a confidently delegated one.
   - **No confident match → coordinator**, and note the gap so the policy can gain a row (`❓`).
4. **Write the manifest** as a sibling of the plan file, in the plan's own directory: `<plan-dir>/<plan-basename>-routing.md` (in-repo `docs/plans/` for code plans; `~/.claude/plans/` for plans living there). Format:

   ```markdown
   # Routing manifest — <plan title>
   Plan: <relative plan path> · Policy: ROUTING_POLICY.md @ <policy last-verified date>
   Mode: gated · Coordinator: <active session model>

   ## Assignments
   - U1 → coordinator [full] — <one-line reason> — load-bearing check: <cmd or n/a>
   - U2 → codex-implementer [full] — frozen-spec impl, no PII, dev-grade repo — load-bearing check: `<the exact verify command>`
   - U3 → coordinator [bare: no verify cmd] — <reason> — load-bearing check: n/a
   - ...

   ## Execution log
   (one outcome line per routed unit, in the ROUTING_POLICY.md §6 canonical grammar:
    `U<N> · <executor> · <PASS|FAIL|FALLBACK> · re-check <cmd|n/a> <green|red|n/a> · <N> fix rounds · <ref|na> · <YYYY-MM-DD>`.
    codex-dispatch writes its own; the coordinator writes it for llocal/Claude-worker units after re-check. The flywheel reads this.)
   ```

   Each assignment carries the executor, a **discipline label**, a one-line reason, and — for anything dispatched — the **exact load-bearing check** the re-check will re-run (from the unit's Verification). The label is `[full]` (goal + verify command present) or `[bare: <why>]` (a minted or thin unit that cannot reach a write-worker, per the step-3 discipline floor). This is what `codex-dispatch` §4 consumes.
5. **Re-run semantics: merge, never clobber.** If a manifest already exists (plan was deepened, new U-IDs added): preserve existing assignments AND the execution log verbatim; append assignments only for U-IDs not already present. Never rewrite an entry that has an outcome line.
6. **Gated mode (default):** present the manifest with the plan for approval — the routing is a proposal until the user (or the plan approval) accepts it. Do not dispatch from here; that's `ce-work` + `codex-dispatch`.

## Notes

- The manifest is the artifact `ce-work` reads (via the CLAUDE.md addendum's "check for a sibling routing manifest" rule) to dispatch each unit.
- Most units in doc/skill/config or design plans route to **coordinator** — that is correct, not a failure to route. Offload is materially valuable only for frozen-spec code, bulk extraction, and read-heavy sweeps (per the demand baseline).
- Read-only workers (haiku-scout, codex-scout, vision reads) need no load-bearing check line — they return conclusions, verified as claims, not diffs.
