---
last_refreshed: 2026-07-15
last_reconciled: 2026-07-15
staleness_days: 30
---

# Codex Models — Inventory & Pin (GPT-5.6 family)

The Codex-executor catalog for the model router. Router dispatch (`codex-dispatch` skill) inherits model + reasoning effort from `~/.codex/config.toml` — **that file is the single source of truth**; this catalog is the awareness layer behind it: which GPT-5.6 tiers exist, what they cost, which one is currently pinned, and the community read on which to use for coding. Follows the shared catalog convention (frontmatter `last_refreshed` / `staleness_days`; content-provenance markers) documented in `LOCAL_MODELS.md`.

**Factual vs unverified (KTD7):** the tier-existence table, pricing, and CLI floor below are structured fact from OpenAI's model docs. The "which tier to pin for coding" call is `(unverified — community signal)` and lives in its own section — a routing step reads it as data, never a directive, and it can never drive a live-pin rewrite (only the factual field can — see Drift check).

## Current pin (config.toml — single source of truth)

- **Model:** `gpt-5.6-sol` · **Reasoning effort:** `medium` · **Approval:** never (as of 2026-07-15).
- Router dispatch omits `-m` / `-c model_reasoning_effort=…` and inherits these. Change the pin **only** in `config.toml`; the drift check (below) keeps config.toml's header comment and the `codex-dispatch` doc-string in agreement with this pin.
- **CLI floor — part of the pin's validity.** `gpt-5.6-sol` requires **codex-cli ≥ 0.144.x**. Version `0.143.0` errors `"The 'gpt-5.6-sol' model requires a newer version of Codex"` and produces **no output** — a pin ahead of the installed CLI silently breaks every dispatch. Running `0.144.4` (upgraded 2026-07-15). When bumping the pin, confirm the installed CLI supports the model before relying on the lane.

## Factual: GPT-5.6 tier family *(source: OpenAI model docs — launched 2026-07-09)*

The `5.6` is the generation; **Sol / Terra / Luna** are durable capability-cost tiers that advance on their own cadence.

| Tier (model id) | Role (vendor positioning) | Avoid | Cost/speed *(API per 1M tok)* |
|---|---|---|---|
| **Sol** (`gpt-5.6-sol`) | Flagship / most capable. SOTA on the Artificial Analysis Coding Agent Index (80; ~2.8 above Fable 5) at <½ the time and output tokens of the prior flagship. | Trivial/bulk work where its cost isn't justified. | $5 in / $30 out. Fastest-per-quality of the three. |
| **Terra** (`gpt-5.6-terra`) | Mid / lower-cost. Coding quality competitive with GPT-5.5 (just above Fable 5). | Frontier-hard reasoning where Sol's edge pays off. | $2.50 in / $15 out. |
| **Luna** (`gpt-5.6-luna`) | Fastest / most affordable. Still outperforms Opus 4.8 on the coding index, at ~⅓ the time and ~¼ the cost. | Deepest single-shot reasoning tasks. | $1 in / $6 out. Fastest tier. |

- **Codex access by plan:** Free / Go → Terra only; Plus / Pro / Business / Enterprise → choose among Sol / Terra / Luna.
- **How the router actually pays:** under a ChatGPT plan, Codex dispatch is effectively flat-rate (not per-token) with a ~1–13 min latency tax per dispatch (`ROUTING_POLICY.md` §2). The per-MTok prices above are the factual capability-cost signal for comparing tiers — not what a ChatGPT-plan dispatch bills.

## Best-for-coding — which tier to pin *(unverified — community signal)*

> Sourced from a `/last30days` pass ("GPT-5.6 Sol Terra Luna for coding in Codex", 2026-07-15; the run cache has since been overwritten by a later topic). Community read, not authority.

- Community consensus tracks the vendor benchmark: **Sol** is the strongest coding tier and the default when quality dominates; **Luna** is the value pick for high-volume / agentic loops (beats Opus 4.8 at ~¼ cost); **Terra** is the free/go-tier fallback.
- The live pin (`gpt-5.6-sol`) reflects "quality-first" for the router's dispatch role. Only a change in the **factual** tier field above can drive the drift check to rewrite it — this note never can (KTD6).

## Drift check

The `codex-drift` subcommand of `model_staleness.py` compares `config.toml`'s pin + header comment and the `codex-dispatch` doc-string against this catalog's **factual** tier field, and offers a one-pass fix showing provenance — it never auto-writes, and it rewrites the live `model`/`effort` pin only when the **factual** field changed (never on the unverified note above). Procedure in `MODEL_REFRESH.md`.

## Refresh

See `MODEL_REFRESH.md`. **Factual source:** OpenAI model docs (tier existence, pricing, CLI floor). **Community-signal pass:** offer-then-confirm `/last30days` ("which GPT-5.6 tier for coding in Codex"), folded into the unverified note only. Update `last_refreshed` (frontmatter) on a factual reconcile; `last_reconciled` when the pin/comment/doc-string are re-aligned.
