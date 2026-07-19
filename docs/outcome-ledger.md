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

## The maintainer's own results (not your starting state)

The shipped table starts every cell at `❓` on purpose — your confidence has to come from *your* stack's outcomes, not mine. This section is the opposite end of that arc: what the ledger looks like after a real proving campaign, so you can see the mechanism actually resolve a cell rather than just trusting the rules describe something real.

Two cells earned `✅` on my own stack, each by the exact rule the spec states — accumulated `PASS` lines with ≤1 fix round, surviving the coordinator re-check, signed off by hand:

- **`impl-from-frozen-spec → codex-implementer`** flipped after **6 clean integrations** across several real build sessions (frozen-spec units — a data-layer helper, a schema regeneration, a token-hardening pass, a filtered-view feature, a logging/error-path hardening, an operational script). Every one dispatched into a credential-scrubbed worktree, came back, survived an independent re-run of its load-bearing check, and merged with 0–1 fix rounds. The single "fix round" in the set was in a generated *test fixture*, never in the implementation — which is exactly why the threshold counts fix rounds, not just PASS.

- **`adversarial / second-opinion review → codex-scout`** flipped after **4 clean gate runs**. The load-bearing observation: on multiple sweeps the independent-model reviewer *reproduced real defects* — a concurrent-boot crash, a session-fixation hole, an integer-overflow, a broken personalization contract — and on the same sweeps a same-family reviewer caught defects the independent one missed. The two passes were **convergent on the worst bugs and complementary on the rest**. A single-model review, however good, is one distribution of blind spots; a second independent model is the cheapest way to cover a different one. Every finding was re-verified by the coordinator before it drove a change — the scout *proposes*, the re-check *confirms*.

### What this is not

It is **not** a reason to pre-flip your own table. Nothing here was measured on your machine, your models, or your work, so by the policy's own rule (*"external evidence suggests; only local outcomes verify"*) it can't flip a cell for you — it can only tell you the arc is real and worth walking. Route your first shape-matched, verifiable, constraint-clean unit *out* as a bake-off trial, let the coordinator re-check be the taster, and let your ledger earn its own `✅`.
