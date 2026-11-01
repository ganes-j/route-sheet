# Narrow fixtures hid two local-drift parser bugs — test the general and the missing form

**Area:** `bin/model_staleness.py` (`_OLLAMA_TAG_RE`, the `Local Model Inventory` section parse), the local-drift reconciler.
**Date:** 2026-07-22. Fixed in PR #16 (`bb382a1`).

## Problem

local-drift compares the models Ollama reports as installed against the `LOCAL_MODELS.md` inventory table. Two bugs reached review with a green suite of 8 unit tests; dual-review caught both, the tests caught neither:

1. **Namespaced and uppercase model IDs were dropped.** `_OLLAMA_TAG_RE` accepted only lowercase, colon-tagged, slash-free IDs. A pulled `host/user/model` or a `...GGUF` / `Qwen/...` ID did not match, so it vanished from the installed set and was reported as drift.
2. **A missing catalog heading looked like wholesale drift.** If the `Local Model Inventory` heading was renamed or absent, the listed set came back empty and every installed model was reported `missing_from_table`, a confident and entirely false result.

## Root cause

Every fixture used the author's mental model of the input: lowercase colon-tagged IDs and a well-formed catalog. The regex and the section lookup were written to that same model, so the tests confirmed the assumption instead of testing it.

## Fix

- Broadened the tag charset to `[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?`, covering namespaces and uppercase.
- An absent inventory heading now returns `status: parse_error` with a message naming the missing section, not a drift report.

## Prevention

- **A content scanner or parser needs at least one fixture in each general or edge form**: namespaced, uppercase, and a missing section. The happy lowercase case alone is not coverage.
- **When a parse finds nothing, ask whether "nothing" is a finding or a failure to parse.** An empty set that turns into "everything is missing" should be a parse error.
- Same failure family as `2026-07-21-openrouter-catalog-naming-reconciliation.md`: fixtures encode the author's assumption, which is exactly the assumption that was wrong.
