# The routing policy format

`ROUTING_POLICY.md` is the system's brain: a single, human-readable, hand-editable markdown file the agent consults at plan time and ad-hoc dispatch time. This page specifies its format so you can adapt the [shipped template](../templates/ROUTING_POLICY.md) with confidence. The design bet is **policy-as-markdown**: no config DSL, no database — a document both the human and the agent read, diff, and edit, with a grammar strict enough for the learning step to parse.

## Section map

| § | Section | Owns |
|---|---|---|
| 1 | Constraint layer | Hard gates checked BEFORE the table — always win. See [security-model.md](security-model.md). |
| 2 | Task-shape → executor table | The routing judgment: shape rows, preferred executor, confidence cell. |
| 3 | Cell format & flip thresholds | How confidence is recorded and what evidence changes it. |
| 4 | Evidence rules | What counts as proof (outcomes) vs suggestion (research). |
| 5 | Drift log | Append-only record of execution deviating from assignments. |
| 6 | Outcome-line grammar | The data contract every executor's completion line follows. See [outcome-ledger.md](outcome-ledger.md). |
| 7 | Gate-iteration protocol | What the coordinator may do with review-gate feedback: correction vs addition, propose-confirm-dispatch. |

## §2 — task shapes, not task topics

Routing keys on the *shape* of a unit, not its subject: `impl-from-frozen-spec`, `bugfix-with-known-repro`, `mechanical-refactor`, `CI/dep/test-bulk`, `batch-extraction`, `PII-batch classification`, `vision/OCR batch`, `huge-context sweep`, `adversarial/second-opinion review`, `large-context code read`. A shape captures what makes a unit delegable: how frozen the spec is, how mechanical the work is, how verifiable the output is. New shapes get added as `❓` rows when routing hits a unit with no confident match.

## §3 — cells as evidence, not opinion

Every (shape → executor) cell carries a confidence state with its evidence trail:

```
state (n=X: breakdown, last YYYY-MM-DD)     e.g.  ✅ (n=4: 3 clean, 1 fallback, last 2026-07-20)
```

- `❓` unknown → `✅` verified-good needs **2+ clean outcomes** (routed, survived the coordinator re-check, ≤1 fix round).
- `✅` → `❌` ruled-out needs a **pattern** — 2–3 consecutive failures or a structural cause. Never a single bad run: one failure is usually a bad spec, not a bad executor.
- Count and date increments apply silently; **state changes need the maintainer's sign-off**.

A fresh install has every cell at `❓`. That is the honest starting state — the table's rows and leans encode judgment, but confidence is earned only through logged outcomes.

## §4 — the evidence hierarchy

**External research suggests; only local outcomes verify.** A web/community research finding may annotate a cell or add a `❓` row; it can never flip a cell to `✅`. This keeps the policy grounded in *your* stack's observed behavior rather than the internet's opinion of a model.

### Seeding a new policy (the demand baseline)

Before any outcomes exist, seed the table from **demand evidence**: retro-route your last ~10 real plans on paper — for each unit, ask which executor *would* have been assigned under the constraint layer. This tells you which shape rows deserve to exist and the initial lean per row (e.g. "frozen-spec implementation shows up constantly; huge-context sweeps never do"). It deliberately does **not** populate cells: retro-routing is not an outcome. Expect the result to be lumpy — in the original seeding, offload demand was bimodal (heavy on credential-clean side-project repos, thin on the credential-laden day-job monorepo), which trimmed the system's scope before it was built.

## §5 — drift as first-class data

When execution deviates from an assignment — circuit-breaker fallback, worker unavailable, coordinator override — a line goes in the drift log with rationale. The flywheel reads drift alongside outcomes: several entries citing the same rationale (say, repeated latency-cited overrides) is **one rule-change proposal**, not N cell tweaks. Drift you don't record is learning you don't get.

## §7 — gate iteration is a decision, not a reflex

A review gate is the user's decision point, so feedback from it is not self-authorizing. §7 forces a line between two things that are easy to conflate: a **correction** (feedback that changes only how a unit meets its *existing* goal/files/verify) stays inside that unit — it inherits the unit's routing and rides as fix rounds on its outcome line. An **addition** (a new deliverable, goal, or surface) is new scope — it needs explicit acceptance and lands as a route-plan mini-pass row or a `## Follow-ons` manifest entry, never riding an existing unit's dispatch. The classification test keys on the unit's spec, not the coordinator's discretion, and the coordinator always **proposes → confirms → dispatches** rather than dispatching remediation in the turn it proposes it. Note the deliberate boundary with §5: a follow-on is *backlog*, not a routing *deviation*, so it stays out of the drift log to keep the flywheel's signal clean.

## Editing rules

- The human can edit anything, anytime — it's a markdown file.
- The agent edits cells only through the flywheel procedure (silent increments; sign-off for state changes) and appends to §5. It never rewrites §1 constraints on its own.
- Keep §6 byte-stable: dispatch skills and the flywheel reference it as the single source of truth rather than restating the grammar, so there is exactly one place format drift can happen.
