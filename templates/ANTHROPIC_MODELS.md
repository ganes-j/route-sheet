---
last_refreshed: 2026-07-15
last_reconciled: 2026-07-15
staleness_days: 30
---

# Anthropic Models — Inventory & Task-Fit

The Anthropic-executor catalog for the model router: which Claude models exist, what each is best for, and what each costs, so a routing decision can compare Claude tiers on capability **and** cost. Follows the shared catalog convention (frontmatter `last_refreshed` / `staleness_days`; content-provenance markers) documented in `LOCAL_MODELS.md`.

**Why this catalog exists (kept in v1 deliberately).** For a route-sheet adopter whose orchestrator is **not** Claude, there is no system prompt naming the current model — this file is their only routing-usable Anthropic source. For the Claude-orchestrator case, the session prompt names the live model but carries no task-fit or price table; this catalog backstops the ambient roster with the comparison data the prompt doesn't hold.

**Factual vs curated (KTD7).** The roster (model IDs, context windows) and per-MTok **pricing** are factual, sourced from the `claude-api` skill's model catalog (cached 2026-06-24, confirmed 2026-07-15) — the authoritative `GET /v1/models` endpoint needs an `x-api-key` + allow-listed host and `ANTHROPIC_API_KEY` isn't in the environment, so the skill catalog is the factual source. The **"best for" / "avoid"** task-fit is hand-curated from each model's published capabilities. A `/last30days` "which Claude model for what" pass (offer-then-confirm) is the unverified-community layer, folded in at refresh and marked as such — none is folded yet.

## Current models (factual roster + pricing; curated task-fit)

| Model | Model ID | Best for | Avoid | Cost/speed *(per 1M tok)* |
|---|---|---|---|---|
| **Fable 5** | `claude-fable-5` | The hardest reasoning and long-horizon autonomous agentic runs; first-shot builds of well-specified systems. | Routine/bulk work (cost); ZDR orgs (unavailable — requires 30-day retention). | $10 in / $50 out. 1M ctx, 128K out. Thinking always on → minutes-long turns at high effort. |
| **Opus 4.8** | `claude-opus-4-8` | The default frontier coordinator: SOTA long-horizon agentic, knowledge work, memory; fast mode available. | Trivial/batch work better routed to Haiku or a local model. | $5 in / $25 out. 1M ctx, 128K out. ~½ Fable's price. |
| **Sonnet 5** | `claude-sonnet-5` | Near-Opus coding/agentic quality at lower cost; high-volume production workloads. | The absolute-hardest reasoning (use Opus or Fable). | $3 in / $15 out ($2/$10 intro through 2026-08-31). 1M ctx, 128K out. |
| **Haiku 4.5** | `claude-haiku-4-5` | Fast/cheap Claude tier for scouts, classification, and simple high-volume tasks — the cheap read tier in `ROUTING_POLICY.md`. | Deep reasoning or correctness-critical work. | $1 in / $5 out. 200K ctx, 64K out. Fastest tier. |

- **Cost gaps (routing-relevant, per `ROUTING_POLICY.md` §2):** a frontier session model (Fable $10/$50, or Opus 4.8 $5/$25) → Haiku ($1/$5) is a ~5–10× drop — the lever behind routing read-heavy scouts to Haiku or bulk work to a local model.
- **Still active, not primary:** Opus 4.7 / Opus 4.6 (`claude-opus-4-7` / `-6`, $5/$25) and Sonnet 4.6 (`claude-sonnet-4-6`, $3/$15) — previous-generation, pin only if needed. **Mythos 5** (`claude-mythos-5`) = Fable-5-equivalent, Project Glasswing participants only.

## Refresh

See `MODEL_REFRESH.md`. **Factual source:** the `claude-api` skill catalog, or `GET /v1/models` when a key is configured (roster + context windows; pricing from the catalog / pricing docs). **Community-signal pass:** offer-then-confirm `/last30days` ("which Claude model for coding / agentic / cost-sensitive work"), folded into task-fit notes only and marked `(unverified — community signal)`. Update `last_refreshed` on a factual reconcile; `last_reconciled` when task-fit is re-curated.
