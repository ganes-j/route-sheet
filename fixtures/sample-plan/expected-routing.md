# Expected routing — fixtures/sample-plan/plan.md

The SETUP.md Phase 4c smoke test passes when your manifest's `## Assignments` matches this table on **executor per U-ID**. Reasons may be worded differently; the load-bearing checks should be equivalent in substance.

| U-ID | Expected executor | Why (per the shipped ROUTING_POLICY.md) |
|---|---|---|
| U1 | `coordinator` | Architecture / spec-writing-as-the-work → never-delegate set (§1). |
| U2 | `codex-implementer` | impl-from-frozen-spec (§2); dev-grade `.env` (localhost + dev key) passes the credential gate worktree-free. Assigned even when Codex isn't installed — the policy routes by shape; codex-dispatch falls back at execution if the binary is absent. |
| U3 | `llocal:<coding model>` | batch-extraction over sensitive customer data → PII-bound work never routes to Codex (§1); mechanical, per-item verifiable → local lane. Any installed coding model qualifies (e.g. `llocal:qwen3.5`). |

Acceptable variances:
- U3 as `coordinator` **only if** the manifest notes the gap "no local model available" — silently absorbing PII work into the coordinator without noting it is a miss.
- Anything else routed to `codex-implementer` or any U-ID missing from the manifest is a **fail**.
