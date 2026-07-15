# Expected routing — fixtures/todo-plan/todo.md

The SETUP.md Phase 4c-bis smoke test passes when route-plan, run against the **ID-less** `todo.md`, mints `[U<N>]` markers (writing them back to the source behind the consent gate) and produces `## Assignments` matching this table on **executor per U-ID AND discipline label**. Reasons may be worded differently; the load-bearing checks should be equivalent in substance.

| U-ID | Expected executor | Discipline | Why (per the shipped ROUTING_POLICY.md + step-3 discipline floor) |
|---|---|---|---|
| U1 | `llocal:<coding model>` | `[full]` | batch-extraction (text) over non-PII legacy strings, per-item verifiable, has a verify command (spot-check + row-count) → local lane (§2). |
| U2 | `codex-implementer` | `[full]` | mechanical-refactor (rename + update callers) with a load-bearing verify (`pnpm test exporter`) → codex-implementer (§2); assigned by shape even if Codex isn't installed (codex-dispatch falls back at execution). |
| U3 | `coordinator` | `[bare: no verify cmd]` | "make the settings page feel snappier" — no inferable verify command → **bare**, so it can never reach a write-worker (step-3 discipline floor); stays coordinator. |
| U4 | `coordinator` | `[bare: no verify cmd]` | "decide … and write the contract" = spec-writing-as-the-work → never-delegate (§1); also bare (the deliverable is a doc, no verify command). |

**The three things this fixture proves (beyond executor-per-U-ID):**
1. **Minting happened** — the manifest carries `[U1]`–`[U4]` for a source that had no `### U<N>.` headings, and (on consent) the markers were written back into `todo.md`.
2. **Full vs bare labels are correct** — U1/U2 `[full]`, U3/U4 `[bare]`.
3. **No bare unit reached a write-worker** — U3 and U4 are coordinator, never codex-implementer or llocal-batch. A bare unit assigned to a write-worker is a **fail**.

Acceptable variances:
- U1 as `coordinator` **only if** the manifest notes "no local model available" (silently absorbing it without noting the gap is a miss).
- A different discipline-label wording is fine as long as the full/bare distinction is unambiguous.
- Anything else — a bare unit on a write-worker, a missing minted U-ID, or no write-back on consent — is a **fail**.
