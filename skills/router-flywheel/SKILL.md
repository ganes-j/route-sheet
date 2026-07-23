---
name: router-flywheel
description: Read model-router outcomes (routing-manifest execution logs + ROUTING_POLICY.md drift log) and propose task-shape cell updates per the §3 flip thresholds. Silent count/date increments; state changes (❓→✅, ✅→❌, new rows) surfaced for the user's sign-off. Invoked by /ce-compound (Phase 1 flywheel), or on request. The reader half of the loop route-plan/codex-dispatch feed.
---

# Router Flywheel (the learning step)

Turn real router outcomes into a better policy. `route-plan` decides and `codex-dispatch`/the coordinator dispatch + write outcome lines (`ROUTING_POLICY.md` §6 grammar); this skill reads them back and proposes cell updates. It **proposes**; the user **disposes** on any state change. Nothing here flips a cell to `✅` on external research or a single run — only accumulated local outcomes.

**Kill switch:** if `~/.claude/.router-off` exists, decline — write nothing, say the router is off.

## Procedure

1. **Load the policy.** Read `~/.claude/ROUTING_POLICY.md`. Missing/malformed → decline; never improvise. Note §3 (thresholds + cell format), §4 (evidence rules), §5 (drift log), §6 (grammar).

2. **R0 gate (dry-run vs live).** Read `~/.claude/ROUTER_STATUS.md` for the `R0 status:` line.
   - **R0 not yet PASSED** → run in **dry-run**: do steps 3–6 and *report* what you would propose, but write nothing to the policy. State the R0 status (e.g. "R0 pending — 1/3 unprompted manifests; flywheel dry-run only"). This lets the mechanism be exercised during the proving period without mutating the policy.
   - **R0 PASSED** → live: proposals can be applied per step 6.
   - **Manual flips are a separate, non-R0-gated path.** R0 gates only *this skill's* automated proposals. The maintainer may sign off a `❓→✅` flip directly on 2+ clean outcomes (`ROUTING_POLICY.md` §3) at any R0 state — the bake-off / proving campaign relies on this, so cells flip on real evidence before organic R0.

3. **Gather outcomes.**
   - Manifests: `~/.claude/plans/*-routing.md` and, when a repo is in play, `<repo>/docs/plans/*-routing.md`.
   - For each manifest, read BOTH `## Assignments` (U-ID → executor + shape hint from the reason) and `## Execution log` (U-ID → outcome line). **Join on U-ID** to map each outcome to a policy cell `(task-shape → executor)`. If the shape isn't explicit in the assignment reason, infer it from the unit; if you can't, skip that line and note it.
   - Also read `ROUTING_POLICY.md` §5 drift log.
   - Parse every execution-log line per the §6 grammar (7 `·`-delimited fields, plus an OPTIONAL trailing `base:<sha>` token). Locate `base:` by its label, not by field position — a line may or may not carry it, and indexing the first seven fields must stay correct either way. `bin/field_records.py:parse_outcome_line()` implements exactly this tolerance if you parse in code rather than by grep.
   - **Read the field-record ledger** (`~/.claude/router-field-records.jsonl`, per §3) via `bin/field_records.py:query_records()`. Each record carries `shape`, `executor`, `kind` (`replay`/`real`/`reverse-replay`), `verify_pass`, optional `margin`, and `unit_ref`. Join records to cells by `(shape → executor)` the same way as outcome lines. **Deduplicate on `unit_ref`:** a routed unit's §6 manifest line and its `real` ledger record are the SAME event — count it once toward flip thresholds, never twice.

4. **Cold-start / no-new-data guard.** No manifests, OR no execution-log lines, OR every line predates the last-verified date of the cell it maps to (nothing new since the cell was last touched) → report "nothing to propose," exit clean. This is the normal state until real routed features accumulate — it is a no-op, not an error. **Never write to the policy on this path.**

5. **Tally + evaluate per cell.** For each `(shape → executor)` cell with new lines:
   - Count **clean** (`PASS`, re-check green, ≤1 fix round), **fail** (`FAIL`), **fallback** (`FALLBACK`).
   - **Evidence class governs what a record can propose (§3 R19):**
     - **`real` / `fallback`** records + `real`-equivalent outcome lines → **flip-eligible** (count toward `❓→✅` / `✅→❌`).
     - **`replay`** records (bake-off evidence) → **eligibility only**: they can support a **challenger-seed proposal** (surface a `❓` seed per §3 seeding) but NEVER flip a cell. Replay margins are directional evidence, not a routed outcome.
     - **Below the R19 decision threshold** (§3: fewer than the minimum records per shape/candidate pair) → **propose nothing** for that cell — not silence-with-a-note, no proposal at all until the floor is met.
   - Apply §3 thresholds (to flip-eligible evidence only):
     - **`❓ → ✅`** — 2+ clean outcomes.
     - **`✅ → ❌`** — a *pattern*: 2–3 consecutive fails or a stated structural cause. Never on a single bad run (one fail is often a bad spec).
     - Otherwise → the cell's counts move but its **state** holds.
   - **Drift patterns** (§5): several entries citing the same rationale (e.g. repeated latency-cited overrides) = **one** rule-change proposal, not N cell tweaks. Surface it as prose, not a cell edit.

6. **Apply vs. surface (only when R0 PASSED — else this is the dry-run report).**
   - **Silent:** count and `last YYYY-MM-DD` increments on cells whose *state* is unchanged. Edit the cell to the §3 format `state (n=X: breakdown, last YYYY-MM-DD)`.
   - **Surface for sign-off:** every **state change** (`❓→✅`, `✅→❌`, new row) and every rule-change proposal — present the proposed change with its supporting outcome lines as evidence, and wait for the user's yes before editing `ROUTING_POLICY.md`. Do not batch a state change into the silent path.

## Notes

- **Read-only workers** (haiku-scout, codex-scout, vision reads) emit `re-check n/a n/a` — their lines count toward *demand/usage*, not toward a re-check-survival flip. Don't flip a read-worker cell on "clean" the way you would a write-worker; treat their conclusions as claims already verified at dispatch.
- **Evidence rule (§4):** an external freshness-research finding may annotate a cell or add a `❓` row; it never flips a cell to `✅`. Only outcomes from this procedure do.
- **This skill never dispatches work** and never edits a plan body or a manifest's assignments — it only reads them and (when live) edits `ROUTING_POLICY.md` cells with sign-off.
- Same-day / re-run safety: a line already reflected in a cell's count (its date ≤ the cell's last-verified date) is not re-counted. When in doubt, prefer under-counting to double-counting.
