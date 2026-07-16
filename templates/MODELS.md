# Model Catalogs — Index

Human/agent-glance index of the three model-awareness catalogs. It holds **no model data of its own** — each catalog is the source of truth for its domain. The refresh mechanism is `MODEL_REFRESH.md`; the staleness helper is `model_staleness.py`.

> This index is for a quick glance only. **Session-start reads the catalogs directly via `model_staleness.py`, not this file** — nothing depends on `MODELS.md`. The staleness snapshot below is re-derived on each refresh (rerun the helper for live state) so the index itself doesn't silently go stale.

## Catalogs

| Catalog | Domain | Factual source | Refresh |
|---|---|---|---|
| [`LOCAL_MODELS.md`](LOCAL_MODELS.md) | Local / ollama models (the `llocal` inventory) | `ollama.com/library` + `llocal models` | [`MODEL_REFRESH.md`](MODEL_REFRESH.md) |
| [`CODEX_MODELS.md`](CODEX_MODELS.md) | Codex executor (GPT-5.6 Sol/Terra/Luna) + the live pin | OpenAI model docs + `~/.codex/config.toml` | [`MODEL_REFRESH.md`](MODEL_REFRESH.md) |
| [`ANTHROPIC_MODELS.md`](ANTHROPIC_MODELS.md) | Anthropic / Claude tiers | `claude-api` skill catalog / `GET /v1/models` | [`MODEL_REFRESH.md`](MODEL_REFRESH.md) |

## Staleness (snapshot 2026-07-15 — re-derived each refresh)

Live state: `python3 model_staleness.py` (non-fresh lines) or `python3 model_staleness.py --json` (all).

| Catalog | State | Last refreshed | Threshold |
|---|---|---|---|
| `LOCAL_MODELS.md` | fresh | 2026-06-25 | 30d |
| `CODEX_MODELS.md` | fresh | 2026-07-15 | 30d |
| `ANTHROPIC_MODELS.md` | fresh | 2026-07-15 | 30d |

States: **fresh** (within `staleness_days`) · **stale** (past it — `ce-plan` offers a refresh, session-start shows a passive line) · **uninitialized** (absent / no parseable `last_refreshed` — "not yet initialized — run setup").
