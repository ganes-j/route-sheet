# Model Routing Policy

The master task-shape → executor table for the model router. Consulted at plan time (by `route-plan`) and at ad-hoc dispatch time (by the coordinator). Model *inventory* facts (install, parallel-viability, versions) live in `LOCAL_MODELS.md`; this file owns *routing*.

**Status:** v1. Codex cells are `❓` until proving runs populate them. Rows and initial leans seeded from a demand baseline (retro-routing your own recent plans — see the seeding note in `docs/routing-policy-spec.md`), which is *demand* evidence (retro-routed plans), not *outcome* evidence — so it sets rows and leans, it does not flip cells.

---

## 1. Constraint layer (overrides the task-shape table — always wins)

These are hard gates checked BEFORE the task-shape table. A task that matches a Codex-friendly shape but trips a constraint does not go to Codex.

- **PII-bound work NEVER routes to Codex** (local or cloud). Always llocal or coordinator. No override, no auto-mode exception. PII status is a property of the *task* (decided at routing time), not the directory.
- **Prod-credential block (the one that gates Codex on a working dir).** Default is **allow** — `.env` presence alone does not block. Block only when the dispatch dir holds a *live prod credential*:
  - a connection string with a **non-localhost host** in any `.env`/config file (the prod-DB case — serious and trivially detectable), OR
  - a file on the **prod deny-list** below.
  - Dev API keys, `localhost`/`127.0.0.1` URLs, and SaaS dev keys **pass**.
  - **On a host-detection block for an authoring unit, scrub into an isolated worktree — do not skip the repo.** Codex units are authoring-only (the coordinator owns execution + the verification gate, per the never-delegate set below), so Codex never needs the credential. Dispatch Codex into a fresh `git worktree` of the repo — a fresh worktree checks out tracked files only, so a gitignored `.env` is not carried in — then **re-run the detection scan against the worktree path**. Clean → dispatch `codex exec -C <worktree>`; the coordinator then reviews the diff, integrates it into the working tree, and runs the load-bearing check + tests against the real env (only the coordinator can — the worktree has no credential). Still-dirty (a tracked / non-gitignored prod credential the worktree can't drop) → **hard-skip** to a non-Codex executor.
  - **Deny-listed dirs (below) hard-skip always — no worktree attempt.** "Known-dangerous" is stronger than "scan came back clean"; a worktree could omit a gitignored deny-listed file and read clean, so the deny-list bypasses the scrub path entirely.
  - Dev-grade dirs (localhost / dev keys) dispatch **directly, worktree-free**. The worktree scrub is only for the host-detection block case — it does not reintroduce worktree ceremony for normal dev checkouts.
  - Detection: grep `.env`/config files in the dispatch dir for `://` values; extract the host (strip `user:pass@`); any host not in {`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `*.local`} → block (or, per the above, scrub-into-worktree then re-scan).
  - **Prod deny-list** (known live-credential files — never send to Codex regardless of scan; replace the example with your own):
    - `~/work/payments-app/.env` (holds a live production database URL — EXAMPLE; list yours here)
    - *(append as encountered)*
  - **Verified dev-grade (Codex-eligible as-is; examples — record your own as you verify them):**
    - `~/work/main-app/apps/api/.env` (two dev API keys, no DB URL)
    - `~/work/main-app/apps/admin/.env` (localhost URLs + short dev secrets)
- **`codex cloud exec` = explicit per-unit approval, never auto.** It uploads the full repo to OpenAI — a distinct trust boundary from local `codex exec`. Requires a blocking yes/no per unit. Never selected by a latency/fan-out threshold. Never in auto mode.
- **Lane A (`ce-work-beta delegate:codex`) activates by typed argument only.** `work_delegate: codex` is NEVER persisted in any repo's `.compound-engineering/config.local.yaml` (ce-work-beta's config chain never consults the kill switch, so a persisted value would delegate while the router is off). Seed `work_delegate_sandbox: full-auto` only (sandbox key, never the activation key). ce-work-beta's yolo recommendation is always declined on work repos.
- **Never delegate (stays on coordinator):** architecture / API design, spec-writing-as-the-work, tiny edits (<~20 lines / single obvious change), anything needing session-scoped tools (MCP, browser, password-manager/secrets), destructive ops, GitHub mutations, the verification/review gate itself.

---

## 2. Task-shape → executor table

Match a unit's shape to a row; apply the constraint layer first. Cell = confidence that the executor handles that shape well, from real router outcomes.

| Task shape | Preferred executor | Cell | Notes |
|---|---|---|---|
| impl-from-frozen-spec | codex-implementer | ❓ | Highest baseline demand. Needs frozen approach + per-unit tests. Credential-clean or dev-grade `.env` only. |
| bugfix-with-known-repro | codex-implementer | ❓ | Repro + expected behavior in the unit. |
| mechanical-refactor | codex-implementer | ❓ | Extract/rewire with tests; no design latitude. |
| CI/dep/test-bulk | codex-implementer | ❓ | Test authoring / dep bumps / tooling scripts from clear spec. |
| batch-extraction (text/JSON) | llocal (coding model) | ❓ | Bulk structured extraction. Verify every item (llocal drops on timeout). |
| PII-batch classification | llocal (coding model) | ❓ | Constraint layer forces local. Keep a deterministic ground-truth path. |
| vision / OCR batch | llocal (vision model) | ❓ | Image → text. |
| huge-context sweep | codex-scout OR haiku-scout | ❓ | Read-only. haiku for cheap/fast; codex-scout when one big working context or an independent model helps. **Zero demand on execution plans** (baseline) — value is in research/planning, ad-hoc. |
| adversarial / second-opinion review | codex-scout | ❓ | Read-only, independent model. Note: reviewing Codex-*written* output is a never-delegate gate. |
| large-context code read / "where is X" | haiku-scout | ❓ | Cheapest read tier. |

**Coordinator-relative rate gap.** Offload pays more the wider the coordinator↔worker cost gap. Read the active session model at plan time: a frontier-tier session model → gap to Haiku is ~10x, offload is cheap; a mid-tier session model → gap ~5x. Codex under a ChatGPT plan is flat-rate (near-zero marginal until the usage window) but carries a minutes-scale latency tax — worth it for work that takes minutes anyway, a loss for small synchronous edits.

---

## 3. Cell format & flip thresholds

Each cell: `state (n=X: breakdown, last YYYY-MM-DD)` — e.g. `✅ (n=4: 3 clean, 1 fallback, last 2026-07-20)`.

- **States:** `✅` verified-good · `❌` ruled-out · `❓` unknown (benchmark once, then record — never re-derive).
- **`❓ → ✅`** requires **2+ clean outcomes** (routed, survived the coordinator re-check, ≤1 fix round).
- **`✅ → ❌`** requires a **pattern** — 2–3 consecutive failures or a structural cause. Never flip on a single bad run (one failure is often a bad spec, not a bad executor).
- Increments and date stamps apply silently; **state changes (`✅`↔`❌`, new rows) need the maintainer's sign-off.**

### Bake-off window — how a `❓` cell earns its verdict (the exploration budget)

A `❓` is **not** a reason to fall back to the coordinator — it's a standing invitation to gather 2–3 real outcomes and resolve the cell fast. The coordinator re-check bounds the downside (a wrong outsource is caught and redone, never shipped), so exploration is cheap: the default for a **verifiable, constraint-clean, cleanly-shape-matched** unit is to route it to the row's candidate executor as a **bake-off trial**, not to keep it in-house. `❓` means *run the bake-off*, not *play it safe*.

- **The re-check is the taster.** A trial **wins** = PASS, survived the coordinator re-check, ≤1 fix round; **loses** = re-check red / FALLBACK / >1 fix round. A **literal A/B** (candidate *and* coordinator on the same unit, compare) is the higher-fidelity option, reserved for expensive shapes where one head-to-head beats 3 serial trials.
- **Window = 2–3 trials per shape, early-stop.** 2 wins → `❓→✅`, close the window (don't keep testing a proven cell). 2 losses → `❓→❌` lean (after a look at bad-spec-vs-bad-fit — §3's "pattern, not one run"). 1–1 → the 3rd breaks the tie. The flip still needs the maintainer's sign-off.
- **Cost-aware — 2–3 is a ceiling, not a quota.** Cheap shapes (bulk extraction, small frozen-spec, where-is-X reads) spend the full window on real matching units freely. Expensive shapes (huge-context sweeps, large impls, latency-heavy Codex on a critical path) use the **smallest genuine representative unit**, or **one A/B**, or **defer** the bake-off to the next low-stakes matching unit — never force an expensive trial onto a critical path.
- **Tag it.** A bake-off dispatch is logged as an **exploration** trial (manifest / ad-hoc outcome ledger), so a loss reads as *data*, not a failure to explain away.
- **The window never opens for** (constraint layer + discipline floor still win): never-delegate shapes, PII / prod-credential-blocked units, and **bare units with no verify command** — no re-check = no taster = no safe bake-off. Route-out-at-`❓` applies only to verifiable, constraint-clean, shape-matched units.

**Shipping router changes (fast-track).** Policy edits, catalog mirrors, proving-outcome logs, and cell flips ship as PRs to the ruleset-protected `main` (audit trail) on a **fast track — no required review, no wait for a separate merge request**: the coordinator opens the PR and self-merges (squash) immediately. The `main` ruleset enforces the flow (require-PR + no force-push/deletion) without gating on review or thread-resolution; advisory bot review may comment but never blocks. The one carve-out: a **cell state-change** (`❓→✅` / `✅→❌`) still gets the maintainer's §3 decision sign-off — surfaced for a yes — after which its flip PR fast-tracks like the rest.

---

## 4. Evidence rules

- **External research suggests; only local outcomes verify.** A freshness-research finding (a scoped web/community search, staleness-triggered on >90-day cells, offer-then-confirm) may annotate a cell or add a `❓` row. It NEVER flips a cell to `✅` — only real router outcomes do.
- The demand baseline (retro-routing your recent plans) sets which rows exist and the initial lean per row; it does not populate cells (retro-routing ≠ outcome).

---

## 5. Drift log (append-only)

When execution deviates from a routing assignment (circuit-breaker fallback, worker unavailable, coordinator judgment override), append a line here with rationale. The compounding/learning step reads this section + manifest outcome lines to propose cell updates. A pattern across entries (e.g., repeated latency-cited overrides) is a rule change, not N cell tweaks.

*(none yet)*

---

## 6. Outcome-line grammar (the flywheel's data contract)

Every routed unit emits **one** outcome line when it completes. Writers (codex-dispatch, and the coordinator for llocal/Claude-worker units) emit this exact shape; the `router-flywheel` reader parses exactly it. This section is the single source of truth — dispatch skills reference it rather than restating a divergent format.

**Home of the line:** a planned unit's line goes in its plan's routing-manifest `## Execution log`. Ad-hoc work with no manifest appends to `~/.claude/router-adhoc-outcomes.md` (append-only).

**Grammar** (single line, `·`-delimited — greppable, no parser needed):

```
U<N> · <executor> · <PASS|FAIL|FALLBACK> · re-check <cmd|n/a> <green|red|n/a> · <N> fix rounds · <ref|na> · <YYYY-MM-DD>
```

- **`U<N>`** — the plan U-ID. For ad-hoc work with no plan, use a short slug (e.g. `adhoc:catalog-extract`).
- **`<executor>`** — a policy executor name: `codex-implementer`, `codex-scout`, `llocal:<model>`, `haiku-scout`, `coordinator`.
- **status** — `PASS` (routed, survived the coordinator re-check) · `FAIL` (re-check red / empty diff / out-of-scope touch / hang) · `FALLBACK` (routed but the coordinator took over — always paired with a §5 drift line).
- **`re-check <cmd> <green|red>`** — the load-bearing command the coordinator re-ran, and its result. **Read-only workers** (scouts, vision reads) have no diff to re-run → `re-check n/a n/a`; their conclusions are still verified as claims, they just emit no command.
- **`<N> fix rounds`** — coordinator fix rounds after the worker's output before it passed (`0` = clean first try). A "clean" outcome for flip-counting (§3) = `PASS` with ≤1 fix round.
- **`<ref>`** — Codex session-id, llocal batch id, or `na`.
- **date** — `YYYY-MM-DD` the line was written (the reader treats a line as "new" if dated after the target cell's last-verified date).

**Required-field rules by executor class:**
- **Write-workers** (`codex-implementer`, llocal batch, coordinator writes): `re-check` must carry a real command + result; `<N> fix rounds` required.
- **Read-workers** (`codex-scout`, `haiku-scout`, vision reads): `re-check n/a n/a`, `0 fix rounds`.

**Examples:**
```
U2 · codex-implementer · PASS · re-check `pnpm test parser` green · 0 fix rounds · 01JABC…session · 2026-07-20
U5 · llocal:qwen3.5 · PASS · re-check spot-checked 12/12 items green · 1 fix rounds · batch-7f3 · 2026-07-21
U3 · haiku-scout · PASS · re-check n/a n/a · 0 fix rounds · na · 2026-07-21
U4 · codex-implementer · FALLBACK · re-check `pnpm build` red · 0 fix rounds · 01JXYZ…session · 2026-07-22
```

---

## 7. Gate-iteration protocol (what the coordinator may do with review-gate feedback)

When a plan defines a review gate (a checkpoint where the user reviews a unit's output before later units proceed) and that gate produces feedback, this section governs what happens next. It closes a gap that let feedback be treated as its own authorization: the coordinator dispatching remediation in the same turn it proposed it, with no line between fixing a unit and adding new scope.

**7.1 Classify each feedback item — the test keys on the unit's own spec.**
- **Correction** — the feedback changes only *how a unit meets its existing goal / files / verify*. It stays inside that unit's scope.
- **Addition** — the feedback adds a *new deliverable, goal, or surface not in any unit's spec*.
- The coordinator applies this test and **states its classification** as part of the confirm beat (7.3); the user can override. The test is mechanical on purpose — "it came up at the gate" does not make it a correction, and net-new work is never smuggled in as "iteration."

**7.2 Corrections inherit; additions get a row.**
- A **correction** inherits its unit's existing executor assignment and rides as additional **fix rounds** on that unit's outcome line (§6). The unit's assignment covers its own iteration — this is the part that is already coherent.
- An **addition** never rides an existing unit's dispatch. On explicit acceptance it lands as either (a) a **new manifest row** via a route-plan mini-pass (next highest sequential U-ID, one new Assignments row, merge-never-clobber — see the route-plan skill), or (b) a **logged follow-on** for later. The coordinator proposes which; the user picks. A logged follow-on goes in the manifest's `## Follow-ons` section — **not** the §5 drift log (§5 feeds the flywheel's cell-update proposals; a deferred addition is backlog, not a routing deviation, and would pollute that signal).

**7.3 Propose-confirm-dispatch — always.**
- Gate feedback is never self-authorizing. The coordinator **proposes** (classification + the remediation + its executor), waits for an explicit **go**, then **dispatches**. This holds even for in-scope corrections: the correction rides the unit's routing, but the *dispatch* still needs the confirm beat. Propose-and-dispatch in a single turn is the prohibited pattern.

Outcome lines for gate iterations follow §6 unchanged: a correction adds fix rounds to the existing unit's line; an accepted addition that becomes a new row gets its own line.
