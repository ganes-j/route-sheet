# The outcome ledger

Every routed unit ends its life as **one line** in a canonical grammar. The line is the unit's done-condition — "no line, no learning" — and the accumulated lines are the only input the flywheel is allowed to learn from. This page is the rationale; the normative grammar lives in [`ROUTING_POLICY.md` §6](../templates/ROUTING_POLICY.md) (single source of truth — dispatch skills reference it rather than restating it, so there is exactly one place format drift can happen).

## The grammar

```
U<N> · <executor> · <PASS|FAIL|FALLBACK> · re-check <cmd|n/a> <green|red|n/a> · <N> fix rounds · <ref|na> · <YYYY-MM-DD>
```

```
U2 · codex-implementer · PASS · re-check `pnpm test parser` green · 0 fix rounds · 01JABC…session · 2026-07-20
U5 · llocal:qwen3.5 · PASS · re-check spot-checked 12/12 items green · 1 fix rounds · batch-7f3 · 2026-07-21
U3 · haiku-scout · PASS · re-check n/a n/a · 0 fix rounds · na · 2026-07-21
U4 · codex-implementer · FALLBACK · re-check `pnpm build` red · 0 fix rounds · 01JXYZ…session · 2026-07-22
```

## Why this shape

**`·`-delimited, one line, greppable.** No parser, no JSON, no schema versioning. `grep ' · codex-implementer · ' ~/.claude/plans/*-routing.md` is the whole query engine. The grammar is strict enough for the flywheel to parse mechanically and loose enough to write by hand.

**The U-ID is the join key.** A manifest's `## Assignments` maps U-ID → (executor, shape); its `## Execution log` maps U-ID → outcome. Joining the two turns each line into evidence for exactly one policy cell `(task-shape → executor)`. That join is what makes the ledger a learning input instead of a diary.

**`re-check` carries the trust boundary into the record.** The status isn't "the worker said done" — `PASS` *means* "survived the coordinator's independent re-run of the load-bearing check." Write-workers must log a real command and its result; read-workers (scouts, vision reads) log `re-check n/a n/a` because they produce claims, not diffs — their lines count toward demand, never toward a re-check-survival flip.

**`fix rounds` separates clean from salvaged.** A `PASS` after four coordinator fix rounds is not evidence the executor handles the shape well. The flip threshold counts only *clean* outcomes: `PASS` with ≤1 fix round.

**`FALLBACK` is paired data.** When the coordinator takes a unit over, the line records it AND a rationale goes to the policy's drift log (§5). One fallback is noise; a pattern of same-rationale fallbacks is a rule-change proposal.

**The date bounds re-counting.** The flywheel treats a line as new only if dated after the target cell's last-verified date — so re-runs and same-day invocations under-count rather than double-count.

## Where lines live

| Work | Home |
|---|---|
| A planned unit | Its plan's routing manifest, `## Execution log` |
| Ad-hoc work (no plan) | `~/.claude/router-adhoc-outcomes.md`, append-only, with a slug instead of a U-ID (`adhoc:catalog-extract · …`) |

**Who writes the line:** `codex-dispatch` writes its own after its re-check; for llocal and Claude-worker units, the coordinator writes it after re-checking the output. Every executor class — including the coordinator itself — emits a line, so the ledger captures the *whole* plan's routing picture, not just the delegated slice.

## The ledger as audit trail

Beyond learning, the ledger answers questions no runtime router can: *what ran where, on whose say-so, verified how?* Each manifest is a signed-off routing decision; each outcome line is the verification receipt. If a delegation ever goes wrong, the trail from "assigned by policy §2 row X" to "re-check red, reverted, FALLBACK, drift-logged" is already written — in plain text, in your repo.
