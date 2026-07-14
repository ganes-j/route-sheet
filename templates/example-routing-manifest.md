# Routing manifest — feat: Add invoice-export service (EXAMPLE — fictional plan)

Plan: docs/plans/2026-03-02-001-feat-invoice-export-plan.md · Policy: ROUTING_POLICY.md @ 2026-02-20
Mode: gated · Coordinator: frontier session model

## Assignments
- U1 → coordinator — API-shape decision (spec-writing-as-the-work) = never-delegate — load-bearing check: n/a
- U2 → codex-implementer — frozen-spec impl, no PII, dev-grade `.env` (localhost only) — load-bearing check: `pnpm test export-service`
- U3 → llocal:qwen3.5 — batch-extraction: classify 1,400 legacy invoice rows into the new category enum (mechanical, verifiable per item) — load-bearing check: spot-check 20 sampled items against ground truth
- U4 → codex-implementer (worktree-scrub) — frozen-spec impl but the repo `.env` holds a non-localhost DB host → scrub into a fresh worktree, re-scan, dispatch there — load-bearing check: `pnpm test export-cron`
- U5 → coordinator — verification gate + PR = never-delegate — load-bearing check: full suite green + preview loads

## Execution log
(one outcome line per routed unit, per ROUTING_POLICY.md §6)

U1 · coordinator · PASS · re-check n/a n/a · 0 fix rounds · na · 2026-03-02
U2 · codex-implementer · PASS · re-check `pnpm test export-service` green · 0 fix rounds · 01JEXAMPLESESSION1 · 2026-03-02
U3 · llocal:qwen3.5 · PASS · re-check spot-checked 20/20 items green · 1 fix rounds · batch-3a9 · 2026-03-02
U4 · codex-implementer · FALLBACK · re-check `pnpm test export-cron` red · 0 fix rounds · 01JEXAMPLESESSION2 · 2026-03-03
U5 · coordinator · PASS · re-check full suite green, preview loads · 0 fix rounds · na · 2026-03-03

<!-- U4's FALLBACK is paired with a drift-log line in ROUTING_POLICY.md §5, e.g.:
     "2026-03-03 · U4 invoice-export cron · codex-implementer → coordinator ·
      Codex diff touched an out-of-scope migration file (scope check failed); coordinator reimplemented." -->
