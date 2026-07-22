---
title: "When a human-edited doc becomes machine input, its prose conventions become parser input"
module: "route_pick.py / ROUTING_POLICY.md §2 candidate matrix"
date: "2026-07-22"
problem_type: design_pattern
component: tooling
severity: medium
applies_when: "Adding a helper/parser that reads a hand-authored markdown table (or any human-edited doc) as structured data — the doc keeps being edited by humans as prose, but a machine now depends on its shape."
tags:
  - "doc-as-data"
  - "markdown-parsing"
  - "deterministic-helper"
  - "dual-review"
  - "candidate-matrix"
  - "dogfooding"
---

# When a human-edited doc becomes machine input, its prose conventions become parser input

**Area:** `bin/route_pick.py` (`_find_row`, `_parse_candidates`) parsing the `ROUTING_POLICY.md` §2 candidate-set matrix.
**Date:** 2026-07-22.

## Context

The candidate-matrix plan turned `ROUTING_POLICY.md` §2 — a table humans hand-edit as documentation — into the input of a deterministic helper (`route_pick.py`) that parses it and returns `(executor, is_bake_off_trial)`. The doc did not change *nature* (still hand-edited markdown), but it gained a second, silent contract: **every cell now has to parse.** Two dual-review findings (both surviving cross-model refutation as high-confidence) were the same root shape — a cell that was perfectly fine as *documentation* was wrong as *parser input*:

1. **Compound prose in a cell that the parser reads as one token.** The huge-context row read `codex-scout OR haiku-scout` — clear to a human, but the parser takes everything before the state glyph as *one executor name* and returned the literal string `"codex-scout OR haiku-scout"`, a non-dispatchable executor. Worse, the read-only check (`"scout" in name`) still accepted it, so it failed *silently*.
2. **Over-permissive matching that a human abbreviation triggers.** `_find_row` matched a shape with `first.startswith(want)`, so a truncated/abbreviated shape (`"batch"`, `"impl"`) silently selected a longer row (`"batch-extraction (text/JSON)"`, `"impl-from-frozen-spec"`) — and the skill prompt and CI smoke test both use shortened shape names, so the footgun was reachable in normal use.

## Guidance

When a hand-edited doc becomes a machine's input:

- **Constrain the cell grammar to what the parser can resolve, and say so in the doc.** A cell must hold *one* parseable value, not prose alternatives. Express "A or B" as either a single preferred value with the alternative in a free-text Notes column, or as distinct entries under an explicit delimiter grammar the parser splits on — never as an un-delimited `A OR B` the parser will swallow whole. (Fix: the row became `haiku-scout ★❓` with the codex-scout escalation moved to Notes.)
- **Match keys exactly or at a word boundary, never by loose prefix.** A prefix match silently binds the wrong row the moment a human writes an abbreviation. (Fix: `first == want or (first.startswith(want) and first[len(want):len(want)+1] in (" ", "("))`.)
- **Fail loud or fail safe, never fail silent-wrong.** The compound-cell bug returned a plausible-looking bogus executor. A parser over human input should return a safe default (here: `coordinator`) on anything it can't cleanly resolve, and its "is this the right kind of thing" checks (`_is_read_only`) must not rubber-stamp a malformed value.
- **Dogfood the parser against the *real* doc, not just fixtures.** Both bugs passed the unit suite (fixtures encode the author's assumptions); they were caught by review reading the actual migrated §2. A CLI smoke step (`route_pick.py "<shape>" --policy <real-file>`) against the shipped doc would have surfaced both.

## Why This Matters

Docs-as-data has a hidden dual contract: the doc must stay readable/editable by humans **and** parse deterministically. Humans edit for the first contract and never see the second — so the failure mode is not a loud parse error, it's a *plausible wrong answer* (a bogus executor name, a silently mis-bound row) that flows downstream. The fixture suite won't catch it because the fixtures were written by the same person who holds the wrong assumption about the grammar. This is the same lesson as the OpenRouter naming-reconciliation learning (dogfood against real data, not fixtures) applied to an *internally*-authored source instead of an external API.

## When to Apply

Any time a helper begins parsing a file that humans hand-edit as documentation — routing tables, config-in-markdown, front-matter conventions, a status matrix. Especially when the same doc is *both* human-facing reference *and* machine input (the §2 matrix is read by people and by `route_pick`).

## Examples

Compound-cell fix (F4):

```
# before — parses to the non-dispatchable executor "codex-scout OR haiku-scout"
| huge-context sweep | codex-scout OR haiku-scout ★❓ | Read-only. haiku for cheap... |
# after — one parseable ★ executor; the alternative lives in Notes as prose
| huge-context sweep | haiku-scout ★❓ | Read-only; ★ haiku for cheap/fast. Escalate to codex-scout when... |
```

Word-boundary match fix (F1/F6):

```python
# before: "batch" silently matches "batch-extraction (text/JSON)"
if first == want or first.startswith(want):
# after: exact, or a prefix that ends at a word boundary
if first == want or (first.startswith(want)
                     and first[len(want):len(want) + 1] in (" ", "(")):
```

Dogfood step that would have caught both (now a CI smoke test):

```bash
python3 bin/route_pick.py "batch-extraction" --policy templates/ROUTING_POLICY.md \
  --verifiable --low-stakes --constraint-clean   # → gpt-oss:20b  trial
python3 bin/route_pick.py "huge-context sweep"  --policy templates/ROUTING_POLICY.md \
  --verifiable --constraint-clean                # → haiku-scout  trial  (not a bogus string)
```

See also: `docs/solutions/2026-07-21-openrouter-catalog-naming-reconciliation.md` (the fixtures-hide-the-bug / dogfood-against-real-data lesson, for an external source).
