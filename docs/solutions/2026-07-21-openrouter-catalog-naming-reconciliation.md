# OpenRouter permaslugs ≠ catalog model IDs — reconcile with a version-aware canonical key

**Area:** `bin/openrouter_discovery.py` (`canonical_key`, `_gate_hosted`), the OpenRouter discovery-digest.
**Date:** 2026-07-21.

## Problem

When the discovery-digest diffed OpenRouter rankings/benchmarks against the three model catalogs, two failures appeared **only against real data** — both passed a full synthetic unit-test suite:

1. **Naming-convention mismatch leaked tracked models as candidates.** OpenRouter and the vendor catalogs name the same model differently. Anthropic is the sharpest case: OpenRouter uses `anthropic/claude-4.8-opus-20260528` (version-then-tier), while the catalog uses the Anthropic-API form `claude-opus-4-8` (tier-then-version). Naive string-matching of normalized IDs never matches them, so **tracked** Opus 4.8 / 4.7 / Sonnet / Haiku / Fable all resurfaced as "new" candidates. (OpenAI/Codex names happen to align — `gpt-5.6-sol` both sides — which is why the bug hid.)
2. **Unranked-hosted flooding.** Surfacing every untracked proprietary model — including ones with no benchmark row (embeddings, `gpt-4o-mini`, previews, old tiers) — buried the signal under ~20 noise rows.

## Root cause

- Discovery matched on the *normalized permaslug string*, assuming OpenRouter and the catalogs share a naming convention. They don't.
- The hosted gate surfaced candidates that couldn't be shown competitive (no benchmark data), contrary to the "surface competitive-or-cheaper, collapse otherwise" intent.

## Fix

- **Version-aware canonical match key** (`canonical_key`): join digit-dash-digit version blocks (`4-8` → `4.8`), then compare *sorted word tokens* and *sorted version tokens* separately. This collapses tier/version reordering (`claude-4.8-opus` ≡ `claude-opus-4-8`, `claude-5-fable` ≡ `claude-fable-5`) while keeping distinct versions distinct (`5.4` ≠ `4.5`, so it doesn't over-suppress a genuinely new model). Tracked-set membership, frontier lookup, and candidate dedup all key on this.
- **Unranked hosted → collapse** (`_gate_hosted`): a candidate with no benchmark coding-index can't clear the frontier, so it collapses under the "+N more" count instead of surfacing.

## Prevention

- **Dogfood matching/discovery logic against real API payloads AND the real catalogs, never just fixtures.** Both bugs survived 24 clean synthetic tests; they surfaced the first time the helper ran against live `list-daily-model-rankings` + `list-benchmarks` diffed against the actual `~/.claude` catalogs. Synthetic fixtures encode the author's assumption about the naming convention — which is exactly the assumption that was wrong.
- When integrating any external model-intelligence source, **the naming-convention reconciliation between that source and the local catalogs is a load-bearing assumption** — verify it explicitly, per vendor, against real data.
- A leak-check that only inspects catalog-form IDs will falsely pass — check for the *source-form* IDs too.
