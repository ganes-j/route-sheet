# route-sheet

Plan-time, policy-driven executor routing for agentic coding. One plan, many models — each implementation unit dispatched to the executor best suited for it, under a security constraint layer, with every outcome logged to an auditable ledger.

The name comes from manufacturing: a route sheet is the document that assigns each operation of a job to a workstation. That's what this does for coding plans.

## Why I built it

I run Claude Code as my daily driver, with OpenAI's Codex CLI and a stack of local Ollama models sitting right there on the same machine. The obvious move is to use all of them — Codex is flat-rate under a ChatGPT plan, local models are free and private, and the frontier model I'm actually talking to is the expensive scarce resource. But every time I reached for delegation ad hoc, I was one lazy moment away from three specific failures:

1. **PII shipped to a third-party executor.** A batch-classification task over customer data routed to a vendor CLI because it looked like a batch-classification task.
2. **A production credential visible inside a vendor sandbox.** `codex exec` pointed at a repo whose gitignored `.env` holds a live production database URL. The sandbox reads the working directory; the credential is now in another vendor's execution environment.
3. **Delegated work confidently reported "done" and never re-checked.** A different model, in its own sandbox, with hidden reasoning, grading its own homework — and the diff landing in my tree on its word alone.

None of the existing routing tools address these, because they all route at the wrong moment. So the rule became: **the routing decision happens at plan time, on paper, under written policy — not at runtime, by vibes.**

## What it is

When a plan is written (I use the [compound-engineering plugin](https://github.com/EveryInc/compound-engineering-plugin)'s `/ce-plan`, which produces plans with stable per-unit IDs), a `route-plan` skill reads a markdown policy file and writes a **sidecar routing manifest** next to the plan — one executor assignment per unit, with a reason and the exact verification command:

```markdown
## Assignments
- U1 → coordinator — API-shape decision (spec-writing-as-the-work) = never-delegate — load-bearing check: n/a
- U2 → codex-implementer — frozen-spec impl, no PII, dev-grade .env — load-bearing check: `pnpm test export-service`
- U3 → llocal:qwen3.5 — batch-extraction, 1,400 rows, verifiable per item — load-bearing check: spot-check 20 items
```

The manifest is approved *with* the plan. At execution, dispatch follows it: Codex units go through a dispatch skill with pre-flight credential guards, local-model units go through a small stdlib CLI ([`llocal`](bin/llocal)), and everything judgment-shaped stays on the coordinator. Every completed unit writes one greppable outcome line — `U2 · codex-implementer · PASS · re-check `pnpm test parser` green · 0 fix rounds · … · 2026-07-20` — and a gated learning step reads those lines back to propose routing-policy updates, which a human signs off.

The full picture, with a diagram: [docs/architecture.md](docs/architecture.md).

## Plan-time vs runtime

Everything else in this space — [claude-code-router](https://github.com/musistudio/claude-code-router), per-inference smart routers, delegation plugins, enterprise AI gateways — decides per request, at runtime, invisibly. That's the right layer for cost optimization. It is the wrong layer for governance, because by the time a request exists, the data is already in the prompt and nobody reviewed the decision.

Routing at plan time gets you three things the proxy layer structurally can't: the decision is **reviewable before anything runs** (the manifest is an artifact you approve, not a log you read later), the decision can use **task-level context** (is this unit's spec frozen? is it PII-bound? does its directory hold a live credential?), and the whole run leaves an **audit trail** — what ran where, on whose say-so, verified how. The full comparison and the "why not just use claude-code-router" answer: [docs/prior-art.md](docs/prior-art.md).

The security constraint layer is the part with no public equivalent I could find: PII never routes to a third-party executor, live prod credentials trigger a scrub-into-worktree path (or a hard-skip for deny-listed dirs), full-repo cloud upload requires explicit per-unit approval, and a defined never-delegate set keeps judgment work on the coordinator. Details and the decision tree: [docs/security-model.md](docs/security-model.md).

## One plan, many models — the plan loop's missing layer

The part I find most interesting is what this suggests about plan-execute loops generally. A good planning workflow already produces the perfect routing substrate: discrete implementation units with stable IDs, frozen approaches, declared file lists, and per-unit verification commands. That's exactly the information you need to decide *who should do each piece* — and today, every planning tool throws it away and executes the whole plan on one model.

route-sheet inserts a dispatch layer between plan and execution. The plan says what to build; the manifest says who builds each piece; the re-check discipline says nothing merges on a worker's word alone; the outcome ledger says whether the assignments were any good. My hope is that plan-time routing becomes a native step in these loops — the U-ID'd plan is the seam, and any plan format that carries stable unit IDs could join the same way.

## Maturity — read this before adopting

This is a young system, published for the pattern more than the code. Concretely, as of July 2026:

- The task-shape routing table ships with **every confidence cell at `❓` (unknown)**. Rows and leans are seeded from retro-routing my own recent plans — that's structured opinion, not measured outcome.
- There has been **one real production dispatch** through the full credential-scrub path: three frozen-spec units on a side project, 3/3 passed the re-check with zero fix rounds. That's evidence the machinery works end to end. It is not a track record.
- The learning flywheel is built and fixture-tested but **runs dry-run until the R0 gate passes** — three consecutive real plans where routing fired unprompted. It refuses to learn from data it doesn't have. I consider this a feature, and it's honest to say the gate hasn't passed yet.
- The read-only scout lanes (codex-scout, haiku-scout) have rows in the policy but drew zero demand in the seeding baseline; the dedicated scout wrapper is deferred.

If you want a battle-tested product, this isn't one. If you want a worked, runnable answer to "how should delegation across vendors be governed on a personal stack," that's what's here.

## Adoption tiers

You don't need the whole stack. Each tier is independently useful and independently verifiable; [SETUP.md](SETUP.md) installs and verifies whichever tier your machine supports.

| Tier | What you get | Needs |
|---|---|---|
| **0 — Read** | The pattern: policy format, constraint layer, manifest, ledger, flywheel gating | Nothing |
| **1 — Policy + manifests** | route-plan writes manifests; coordinator executes everything; kill switch; outcome lines | Claude Code (a U-ID plan workflow helps but isn't required — route-plan mints IDs from an ID-less TODO/tasklist/pasted plan) |
| **2 — + Codex lane** | codex-dispatch with credential scan, worktree scrub, re-check, circuit breaker | Tier 1 + Codex CLI |
| **3 — + local lane** | `llocal` run/batch for bulk, PII-bound, and vision work | Tier 1 + Ollama (+ models) |

## Dependencies

| Dependency | Needed at | Verified against | Without it |
|---|---|---|---|
| [Claude Code](https://claude.com/claude-code) (skills, SessionStart hooks, settings.json) | Tier 1+ | July 2026 builds | The skills and hook have no host. The *documents* still transfer to any agent that reads markdown instructions. |
| [compound-engineering plugin](https://github.com/EveryInc/compound-engineering-plugin) (`/ce-plan`, `/ce-work`, `/ce-compound`) | **Recommended**, Tier 1+ | v3.14.x | Gives you U-ID'd plans for free and the full plan→route→work→compound loop. Not required: route-plan mints stable IDs from an ID-less TODO/tasklist/pasted plan, so any structured input is routable — the plugin makes it nicer, not possible. |
| [superpowers plugin](https://github.com/obra/superpowers) (verification-before-completion discipline) | Recommended, Tier 1+ | July 2026 | The re-check gate loses its enforcement backstop; you must supply the "paste real output before claiming done" discipline yourself. |
| [Codex CLI](https://github.com/openai/codex) + ChatGPT plan auth + `~/.codex/config.toml` model pin | Tier 2 | 0.143.0, `gpt-5.5` pin | Tier 2 unavailable; codex rows in the policy stay dormant. Everything else works. |
| [Ollama](https://ollama.com) + models per [LOCAL_MODELS](templates/LOCAL_MODELS.md) | Tier 3 | v0.24+ (MLX); qwen3.5 35B wants ~24GB+ free unified memory, the ≤7B rows run almost anywhere | Tier 3 unavailable; llocal rows stay dormant. |
| Python 3 (stdlib only) | Tiers 1–3 | 3.9+ | `llocal` and the kill-switch hook don't run. No pip packages needed, ever. |
| git (with worktree support) | Tier 2 | any modern git | The credential scrub path can't isolate; host-detection hits become hard-skips. |

## Repo map

```
docs/          architecture · routing-policy-spec · security-model · outcome-ledger · prior-art
templates/     ROUTING_POLICY · LOCAL_MODELS · claude-md-router-section · ROUTER_STATUS · example manifest
skills/        route-plan · codex-dispatch · router-flywheel   (Claude Code SKILL.md files)
bin/llocal     stdlib-only Ollama CLI (models / run / batch)
hooks/         SessionStart kill-switch context injector
fixtures/      sample plan + expected manifest (SETUP.md's smoke test)
scripts/       leak-check.sh — pre-publish sanitization gate (blocklist stays local, gitignored)
SETUP.md       agent-executable install runbook (tiered, idempotent, verified)
AGENTS.md      orientation for agents consuming this repo
```

## Install

Point your agent at this repo and say: *"Read SETUP.md and set this up for me."* It's written for the agent — capability preflight, consent gates before any write, idempotent marker-bounded edits, per-step verification, and an honest report of which tier you landed on. Humans are welcome to follow it too.

## License

MIT. If you adapt the pattern, I'd genuinely like to hear how the routing table fills in on your stack — that's the data the flywheel design is hungry for.
