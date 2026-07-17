# Concepts

Shared vocabulary for the router — the roles, the policy objects, and the named steps the README, `docs/`, and skills use without re-defining. Glossary only: short entries grouped by theme, not a spec. The full specification lives in [docs/routing-policy-spec.md](docs/routing-policy-spec.md); this file just names things.

## Roles

### Coordinator
The frontier session model you are actually talking to — the one that plans, does the never-delegate work itself, and owns the verification gate. Every routed unit's output returns to the coordinator for a re-check before it counts.

### Executor
Whatever a unit is routed to: `codex-implementer`, `codex-scout`, `llocal`, `haiku-scout`, or the coordinator itself. A routing decision is a choice of executor, one per unit.

### codex-implementer
OpenAI's Codex CLI in write mode — for frozen-spec implementation, bugfix-with-known-repro, mechanical refactor, and CI/dep/test-bulk work. Authoring-only (the coordinator still runs and verifies), and dispatched only into credential-clean or dev-grade directories.

### codex-scout
Codex in read-only mode — huge-context sweeps and adversarial / second-opinion reviews where an independent model helps. Returns conclusions, not diffs. Reviewing Codex-*written* output is never delegated to it.

### llocal
The stdlib CLI ([bin/llocal](bin/llocal)) that runs local Ollama models for bulk text/JSON extraction, PII-bound batch work, and vision/OCR. The constraint layer forces PII-bound work here (or to the coordinator), never to a third-party executor.

### haiku-scout
The cheapest read tier — a small Claude model for large-context reads and "where is X" lookups. Read-only, like codex-scout.

## The policy

### Task shape
What a unit *is* for routing purposes — `impl-from-frozen-spec`, `mechanical-refactor`, `batch-extraction`, `vision/OCR batch`, and so on. Routing keys on shape (how frozen the spec is, how mechanical the work is, how verifiable the output is), never on the unit's topic.

### Task-shape cell
A (shape → executor) entry in the §2 table carrying a confidence state and its evidence trail — e.g. `✅ (n=4: 3 clean, 1 fallback, last 2026-07-20)`. A fresh install has every cell at `❓`.

### Constraint layer
The §1 hard gates checked *before* the shape table, and always winning: PII never to a third-party executor, live-prod-credential handling, per-unit approval for full-repo cloud upload, and the never-delegate set.

### Never-delegate set
The shapes that always stay on the coordinator: architecture / API design, spec-writing-as-the-work, tiny edits, anything needing session-scoped tools (MCP, browser, secrets), destructive ops, GitHub mutations, and the verification gate itself.

### Routing manifest
The sidecar markdown file `route-plan` writes next to a plan — one executor assignment per unit, each with a reason and the exact verification command. Approved *with* the plan; it is what `ce-work` dispatches from.

### Dispatch-is-default-binding
Once a manifest assigns a unit, running it inline anyway — without logging an override — is a verification-gate miss. Deviations get a drift-log line, not silence.

### Fallback ladder
What to do when there is no manifest, or a unit's U-ID is not in it (the plan was deepened after routing): work that unit inline, note the gap, and offer a `route-plan` run. Never improvise routing.

### Demand baseline
The seeding step for a new policy — retro-route your last ~10 real plans on paper to decide which shape rows deserve to exist and their initial lean. It is demand evidence, not outcome evidence, so it sets rows and leans but never populates a cell.

## Verification & evidence

### Coordinator re-check
The discipline that nothing merges on a worker's word: the coordinator reads the diff and re-runs the unit's load-bearing command itself. A routed unit "passes" only if it survives this.

### Outcome line
The single `·`-delimited line every completed unit emits, in the §6 grammar (`U<N> · <executor> · <PASS|FAIL|FALLBACK> · re-check … · <N> fix rounds · <ref> · <date>`). One byte-stable format, so the flywheel parses it without a parser.

### Outcome ledger
The accumulated outcome lines — in a plan's manifest `## Execution log`, or `router-adhoc-outcomes.md` for ad-hoc work. The audit trail of what ran where, on whose say-so, verified how; the flywheel's only input. See [docs/outcome-ledger.md](docs/outcome-ledger.md).

### Circuit breaker
codex-dispatch's guard that stops re-trying a failing Codex unit and falls back to the coordinator instead of looping. The fallback is recorded as a drift-log line.

### Kill switch
The `~/.claude/.router-off` sentinel file. Present → the router is off; work inline, no routing. The SessionStart hook reports the active/disabled state from it.

## The learning loop

### router-flywheel
The gated learning step (run at `/ce-compound`) that reads outcome lines plus the drift log and proposes task-shape cell updates. It proposes; a human signs off.

### Proving runs / proving campaign
The accumulation of real dispatched outcomes per cell that a `❓` needs before it can flip. Cells are earned through logged proving runs, not asserted.

### Bake-off window
The exploration budget for a `❓` cell: route a verifiable, constraint-clean, cleanly-shape-matched unit *out* as a tagged trial (not to the coordinator), 2–3 trials, early-stop — two wins flip it toward `✅`. `❓` means run the bake-off, not play it safe.

### R0 gate
The gate on the flywheel's *automated* proposals: it stays dry-run until routing has fired unprompted on 3 consecutive real plans — "don't auto-learn until it is proven used." Status tracked in [templates/ROUTER_STATUS.md](templates/ROUTER_STATUS.md).

### Dual flip-authorization
The two paths a cell flip can take (the "R0 fork"): the flywheel's automated proposal (R0-gated) *or* the maintainer's direct sign-off on 2+ clean outcomes (not R0-gated). Cell correctness is independent of router adoption, so real evidence can flip a cell even at R0 0/3.

### Drift log
The append-only §5 record of execution deviating from an assignment (circuit-breaker fallback, worker unavailable, coordinator override), with rationale. The flywheel reads it alongside outcomes; a repeated rationale is one rule-change proposal, not N cell tweaks.

### Gate-iteration protocol
The §7 rule for review-gate feedback: classify each item against the unit's spec — a **correction** (changes only how a unit meets its existing goal) inherits the unit's routing and rides as fix rounds; an **addition** (a new deliverable or surface) needs explicit acceptance and its own row. Always propose → confirm → dispatch; never dispatch remediation in the turn you propose it.

## Model catalogs

### The three catalogs
`LOCAL_MODELS.md`, `CODEX_MODELS.md`, and `ANTHROPIC_MODELS.md` — one per executor domain, each carrying per-model task-fit and cost behind a `last_refreshed` date. [templates/MODELS.md](templates/MODELS.md) indexes them; [templates/MODEL_REFRESH.md](templates/MODEL_REFRESH.md) is the refresh procedure.

### Staleness / last_refreshed
Each catalog's `last_refreshed` frontmatter date, measured against its `staleness_days` (default 30), decides fresh / stale / uninitialized — computed by `model_staleness.py`. A stale catalog gets a passive session-start line and a refresh *offer* at `/ce-plan` (the sole conversion surface); the refresh is never auto-run.
