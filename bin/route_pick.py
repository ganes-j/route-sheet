"""Deterministic candidate selection over the ROUTING_POLICY.md §2 matrix.

`pick()` is the executable enforcement of §3's candidate-selection rules
(R3 auto-pick ★, R4 verify-gate, R5 challenger-competes, R6 low-stakes
challenger-scheduling). Given a task shape plus a unit's properties it returns
`(executor, is_bake_off_trial)` — so `route-plan` and ad-hoc dispatch pick the
same executor every time, instead of re-interpreting prose.

The constraint layer (§1) runs UPSTREAM and is passed in as `constraint_clean`
— it is never re-derived here. Parses hand-edited markdown defensively: any
malformed / absent row falls back to the safe coordinator default, never raises.

Stdlib only.
"""

import argparse
import re
import sys

STATES = ("✅", "❌", "❓")
READ_ONLY_MARKERS = ("scout",)  # codex-scout / haiku-scout return conclusions,
#                                 not diffs → no coordinator re-check needed.

# Local-model sizes (GB), the local + factual signal the R3 tiebreak uses.
# Never a benchmark/quality/community field — those are discovery inputs (§4),
# never selection inputs. Unknown model → treated as +inf (loses the tiebreak;
# if every tied candidate is unknown, matrix order decides).
_SIZE_GB = {
    "qwen3.5": 21.9,
    "gpt-oss:20b": 13.0,
    "gpt-oss:120b": 65.0,
    "llava": 8.0,
    "llava:13b": 8.0,
    "llava:latest": 4.7,
    "phi4-mini": 2.5,
    "phi4-mini:latest": 2.5,
    "nomic-embed-text": 0.3,
}


def _size_gb(name):
    return _SIZE_GB.get(name, float("inf"))


def _is_read_only(name):
    low = name.lower()
    return any(m in low for m in READ_ONLY_MARKERS)


def _section_2(text):
    """Lines of the '## 2.' task-shape table section, up to the next '## '."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and re.match(r"##\s*2\b", ln):
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        out.append(ln)
    return out


def _find_row(text, shape):
    """The candidate-column string for `shape`, or None. Matches the first
    table cell exactly, or as a prefix (so 'batch-extraction' matches
    'batch-extraction (text/JSON)')."""
    want = shape.strip()
    for ln in _section_2(text):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0]
        if first.lower() in ("task shape", "") or set(first) <= set("-: "):
            continue  # header / separator row
        if first == want or first.startswith(want):
            return cells[1]
    return None


def _parse_candidates(cell):
    """Parse a ' · '-delimited candidate list into ordered dicts.

    Each candidate: `<executor> [★]<state>[hq] [(evidence)]`. Keys on the first
    state glyph; the leading text (minus the ★ mark) is the executor name. The
    ★ and `hq` qualifier are documentation only — selection computes ★ (R3) and
    the tiebreak deliberately ignores quality signals — so neither is retained.
    Candidates with no recognizable state glyph are skipped (defensive)."""
    candidates = []
    for idx, raw in enumerate(cell.split(" · ")):
        token = raw.strip()
        if not token:
            continue
        pos = None
        state = None
        for glyph in STATES:
            g = token.find(glyph)
            if g != -1 and (pos is None or g < pos):
                pos, state = g, glyph
        if pos is None:
            continue
        name = token[:pos].replace("★", "").strip()
        if not name:
            continue
        candidates.append({"name": name, "state": state, "index": idx})
    return candidates


def _auto_star(candidates):
    """R3: ★ = highest verified cell if any ✅ exists (tiebreak = smaller size,
    then matrix order); else the incumbent-by-lean (first-listed candidate).
    ❌ ruled-out candidates are never eligible."""
    eligible = [c for c in candidates if c["state"] != "❌"]
    if not eligible:
        return None
    verified = [c for c in eligible if c["state"] == "✅"]
    if verified:
        return min(verified, key=lambda c: (_size_gb(c["name"]), c["index"]))
    return eligible[0]


def pick(shape, verifiable, low_stakes, constraint_clean, matrix_text):
    """Return `(executor, is_bake_off_trial)` for a unit matched to `shape`.

    Order mirrors §3 / the selection flowchart: constraint layer → verify-gate
    → challenger-scheduling. `is_bake_off_trial` is True iff the chosen candidate
    is routed on a still-`❓` cell (routing to an unproven cell is itself the
    exploration); the coordinator is never a trial.
    """
    default = ("coordinator", False)
    try:
        # §1 constraint layer (upstream): not clean → coordinator/local only.
        if not constraint_clean:
            return default

        cell = _find_row(matrix_text, shape)
        if cell is None:
            return default
        candidates = _parse_candidates(cell)
        star = _auto_star(candidates)
        if star is None:
            return default

        # R4 verify-gate: no load-bearing verify command → never a write-worker
        # or trial. A read-only scout is fine (no diff to re-check); anything
        # else falls to the coordinator. Never a trial.
        if not verifiable:
            if _is_read_only(star["name"]):
                return (star["name"], False)
            return default

        # R5 challenger-competes + R6 low-stakes scheduling.
        challengers = [c for c in candidates
                       if c is not star and c["state"] == "❓"]
        if challengers and low_stakes:
            chosen = challengers[0]  # first-listed ❓ challenger (deterministic)
            return (chosen["name"], True)

        return (star["name"], star["state"] == "❓")
    except Exception:  # noqa: BLE001 - hand-edited markdown must never crash routing
        return default


def _cli(argv):
    ap = argparse.ArgumentParser(description="Pick an executor for a task shape "
                                 "from a ROUTING_POLICY.md §2 matrix.")
    ap.add_argument("shape")
    ap.add_argument("--policy", default=None,
                    help="path to ROUTING_POLICY.md (default: stdin)")
    ap.add_argument("--verifiable", action="store_true")
    ap.add_argument("--low-stakes", action="store_true")
    ap.add_argument("--constraint-clean", action="store_true")
    args = ap.parse_args(argv)
    if args.policy:
        with open(args.policy, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    ex, trial = pick(args.shape, verifiable=args.verifiable,
                     low_stakes=args.low_stakes,
                     constraint_clean=args.constraint_clean, matrix_text=text)
    sys.stdout.write("%s\t%s\n" % (ex, "trial" if trial else "assign"))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
