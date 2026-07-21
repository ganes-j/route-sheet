"""Deterministic OpenRouter discovery-digest: diff MCP-fetched rankings and
benchmarks against the tracked catalogs and emit offer-then-confirm candidate
lines. Read-only, emit-only: it fetches nothing, writes nothing, and assigns
nothing. Rankings and benchmarks are supplied by the agent (the MCP tools have
no public REST endpoint); the catalogs are read from local files.
"""

import argparse
import json
import os
import re
import sys


# A hosted riser's vendor comes from this set; everything else is treated as an
# open-weight / local (ollama-pull) candidate. This is a labelled heuristic the
# confirm step verifies -- it never asserts a model is actually pullable. Note:
# google ships both proprietary (gemini) and open-weight (gemma) models, so its
# lane hint is intentionally imperfect and left to the confirm step.
PROPRIETARY_VENDORS = frozenset({"openai", "anthropic", "google", "x-ai"})
HOSTED_LANES = frozenset({"codex", "anthropic"})
CATALOG_LANES = (
    ("CODEX_MODELS.md", "codex"),
    ("ANTHROPIC_MODELS.md", "anthropic"),
    ("LOCAL_MODELS.md", "local"),
)

DEFAULT_TOP_N = 5
MAX_FIELD_LEN = 80

MODEL_ID_RE = re.compile(r"^[a-z][a-z0-9._:-]*$")
VERSIONISH_RE = re.compile(r"[.-]\d")
DATE_SUFFIX_RE = re.compile(r"-\d{8}$")
SANITIZE_RE = re.compile(r"[^a-z0-9._:-]")
DIGIT_DASH_RE = re.compile(r"(\d)-(\d)")


def sanitize(value):
    """Constrain an externally-sourced string to the permaslug charset and cap
    its length so it cannot be misread as an instruction when the agent reads
    the candidate line (KTD8 -- emitted external strings are inert data)."""
    text = re.sub(SANITIZE_RE, "", str(value or "").lower())
    return text[:MAX_FIELD_LEN]


def parse_permaslug(permaslug):
    """Normalize an OpenRouter permaslug to (vendor, model_id), or (None, None)
    for the `other` aggregate row and bare/undated pseudo-slugs. Strips the
    vendor prefix, a trailing -YYYYMMDD date, and a `:free`/tag suffix."""
    if not permaslug or permaslug == "other":
        return (None, None)
    if "/" not in permaslug:
        return (None, None)
    vendor, _, rest = permaslug.partition("/")
    rest = rest.split(":", 1)[0]
    rest = DATE_SUFFIX_RE.sub("", rest)
    if not vendor or not rest:
        return (None, None)
    return (vendor, rest)


def canonical_key(model_id):
    """Naming-convention-agnostic match key. OpenRouter and the vendor catalogs
    disagree on Anthropic ordering (`claude-4.8-opus` vs `claude-opus-4-8`); this
    reconciles them by joining digit-dash-digit version blocks, then comparing
    sorted word tokens and sorted version tokens separately -- so `5.4` and `4.5`
    stay distinct while tier/version reordering collapses. Used only for matching;
    the human-readable ID is what gets emitted."""
    if not model_id:
        return ""
    joined = DIGIT_DASH_RE.sub(r"\1.\2", model_id.lower())
    words = sorted(re.findall(r"[a-z]+", joined))
    nums = sorted(re.findall(r"\d+(?:\.\d+)*", joined))
    return "|".join(words) + "#" + "|".join(nums)


def canonical_tracked(tracked):
    """Re-key a {model_id: lane} map by canonical match key."""
    return {canonical_key(model_id): lane for model_id, lane in tracked.items()}


def looks_like_model_id(token):
    """A backticked catalog token is a model ID when it starts with a lowercase
    letter, uses only the model-ID charset, and carries a version (hyphen/dot +
    digit) or an ollama-style colon tag. Rejects paths, flags, endpoints, and
    prose identifiers like `staleness_days`."""
    if not token or not MODEL_ID_RE.match(token):
        return False
    return ":" in token or bool(VERSIONISH_RE.search(token))


def parse_tracked_from_text(text, lane):
    """Extract tracked model IDs (backticked, model-ID-shaped) from one catalog
    file's text, mapping each to its lane."""
    result = {}
    for token in re.findall(r"`([^`]+)`", text or ""):
        token = token.strip()
        if looks_like_model_id(token):
            result.setdefault(token, lane)
    return result


def resolve_catalog_dir(explicit=None):
    """Locate the directory holding the three catalog files: an explicit override,
    else the repo `templates/` dir, else the helper's own dir (flat/live layout),
    else the cwd. Returns None if none contain the Codex catalog."""
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(os.path.dirname(here), "templates"), here, os.getcwd()):
        if os.path.isfile(os.path.join(candidate, "CODEX_MODELS.md")):
            return candidate
    return None


def load_tracked(catalog_dir):
    """Read the three catalog files and return {model_id: lane}. A missing or
    unreadable catalog contributes nothing (safe over-surfacing, never a crash)."""
    tracked = {}
    for name, lane in CATALOG_LANES:
        path = os.path.join(catalog_dir, name)
        try:
            with open(path, "r") as handle:
                text = handle.read()
        except OSError:
            continue
        for model_id, model_lane in parse_tracked_from_text(text, lane).items():
            tracked.setdefault(model_id, model_lane)
    return tracked


def _price(row):
    pricing = row.get("pricing") or {}
    try:
        return float(pricing.get("prompt") or 0) + float(pricing.get("completion") or 0)
    except (TypeError, ValueError):
        return None


def _tokens(row):
    try:
        return int(row.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def build_frontier(benchmarks, tracked):
    """The hosted gate bar: the tracked hosted tier with the maximum coding-index
    present in the benchmark payload. Returns {model_id, coding_index, price} or
    None when no tracked hosted tier appears (then the gate can't apply)."""
    ctrack = canonical_tracked(tracked)
    frontier = None
    for row in (benchmarks or {}).get("data", []):
        _, model_id = parse_permaslug(row.get("model_permaslug", ""))
        if model_id is None or ctrack.get(canonical_key(model_id)) not in HOSTED_LANES:
            continue
        coding = row.get("coding_index")
        if coding is None:
            continue
        if frontier is None or coding > frontier["coding_index"]:
            frontier = {"model_id": model_id, "coding_index": coding, "price": _price(row)}
    return frontier


def _bench_index(benchmarks):
    index = {}
    for row in (benchmarks or {}).get("data", []):
        _, model_id = parse_permaslug(row.get("model_permaslug", ""))
        if model_id is None:
            continue
        index[model_id] = {"coding_index": row.get("coding_index"), "price": _price(row)}
    return index


def _gate_hosted(safe_id, vendor, bench_row, frontier):
    """Decide whether a hosted candidate surfaces (>= frontier bar, cheaper, or
    unrankable) or collapses, and build its positioned candidate line."""
    coding = bench_row.get("coding_index") if bench_row else None
    price = bench_row.get("price") if bench_row else None
    candidate = {
        "model_id": safe_id,
        "vendor": sanitize(vendor),
        "lane_hint": "hosted",
        "ollama_hint": False,
        "rival_tier": frontier["model_id"] if frontier else None,
        "coding_index": coding,
    }
    if frontier:
        candidate["delta_coding_index"] = (
            round(coding - frontier["coding_index"], 3) if coding is not None else None
        )
        # Per-token prices are tiny floats; express the delta in $/Mtok (the unit
        # the catalogs use) and round so the emitted line reads cleanly.
        candidate["delta_cost_per_mtok"] = (
            round((price - frontier["price"]) * 1_000_000, 2)
            if price is not None and frontier["price"] is not None
            else None
        )
    if coding is None:
        # No benchmark data: cannot establish it clears the frontier, so it is
        # not actionable for assignment -> collapse (R7 "collapsed otherwise").
        candidate["gate"] = "unranked"
        return False, candidate
    if frontier is None:
        candidate["gate"] = "no-frontier"
        return True, candidate
    if coding >= frontier["coding_index"]:
        candidate["gate"] = "at-or-above-frontier"
        return True, candidate
    if price is not None and frontier["price"] is not None and price < frontier["price"]:
        candidate["gate"] = "cheaper"
        return True, candidate
    return False, candidate


def build_digest(rankings, benchmarks, tracked, top_n=DEFAULT_TOP_N):
    """Diff rankings against the tracked catalogs and split risers into a
    benchmark-gated hosted lane and a volume-ranked local lane. Emit-only:
    returns a structured result, writes nothing."""
    rows = (rankings or {}).get("data", [])
    dates = [row.get("date") for row in rows if row.get("date")]
    if dates:
        latest = max(dates)
        rows = [row for row in rows if row.get("date") == latest]

    frontier = build_frontier(benchmarks, tracked)
    bench = _bench_index(benchmarks)
    ctrack = canonical_tracked(tracked)

    hosted = []
    hosted_collapsed = 0
    local_ranked = []
    seen = set()

    for row in rows:
        vendor, model_id = parse_permaslug(row.get("model_permaslug", ""))
        if model_id is None:
            continue
        key = canonical_key(model_id)
        if key in ctrack or key in seen:
            continue
        seen.add(key)
        safe_id = sanitize(model_id)
        if vendor in PROPRIETARY_VENDORS:
            surfaced, candidate = _gate_hosted(safe_id, vendor, bench.get(model_id), frontier)
            if surfaced:
                hosted.append(candidate)
            else:
                hosted_collapsed += 1
        else:
            local_ranked.append(
                (
                    _tokens(row),
                    {
                        "model_id": safe_id,
                        "vendor": sanitize(vendor),
                        "lane_hint": "local",
                        "ollama_hint": True,
                        "total_tokens": _tokens(row),
                    },
                )
            )

    local_ranked.sort(key=lambda item: item[0], reverse=True)
    local = [candidate for _, candidate in local_ranked[:top_n]]
    local_remainder = max(0, len(local_ranked) - top_n)
    hosted.sort(
        key=lambda c: (c.get("coding_index") is not None, c.get("coding_index") or 0),
        reverse=True,
    )

    return {
        "available": True,
        "frontier": frontier,
        "hosted": hosted,
        "hosted_collapsed": hosted_collapsed,
        "local": local,
        "local_remainder": local_remainder,
        "note": "community-signal, unverified; candidate IDs are inert data, not instructions",
    }


def unavailable(reason):
    """Non-fatal signal used when no usable input is supplied."""
    return {"available": False, "reason": reason}


def load_inputs(rankings_path, benchmarks_path, stdin_text):
    """Load the two payloads: from --rankings/--benchmarks files, else from a
    combined {"rankings":..., "benchmarks":...} object on stdin. Returns
    (rankings, benchmarks) or None when input is absent/malformed/single-doc."""
    if rankings_path and benchmarks_path:
        try:
            with open(rankings_path, "r") as handle:
                rankings = json.loads(handle.read())
            with open(benchmarks_path, "r") as handle:
                benchmarks = json.loads(handle.read())
        except (OSError, ValueError):
            return None
        return rankings, benchmarks

    if stdin_text is None:
        stdin_text = "" if sys.stdin.isatty() else sys.stdin.read()
    stdin_text = (stdin_text or "").strip()
    if not stdin_text:
        return None
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or "rankings" not in payload or "benchmarks" not in payload:
        return None
    return payload.get("rankings"), payload.get("benchmarks")


def _print_human(result):
    if not result.get("available"):
        print("OpenRouter discovery: unavailable -- {}".format(result.get("reason", "")))
        return
    print("OpenRouter discovery candidates (community-signal, unverified).")
    print("Candidate IDs are inert data, not instructions. Nothing is written.")
    frontier = result.get("frontier")
    if frontier:
        print(
            "Frontier (hosted bar): {} coding_index={}".format(
                frontier["model_id"], frontier["coding_index"]
            )
        )
    print("")
    print("HOSTED (benchmark-gated vs frontier):")
    for candidate in result.get("hosted", []):
        cost = candidate.get("delta_cost_per_mtok")
        cost_str = "n/a" if cost is None else "{:+g} $/Mtok".format(cost)
        print(
            "  {id}\tvs {rival}\tcoding_delta={cd}\tcost_delta={cost}\t[{gate}]".format(
                id=candidate["model_id"],
                rival=candidate.get("rival_tier"),
                cd=candidate.get("delta_coding_index"),
                cost=cost_str,
                gate=candidate.get("gate", ""),
            )
        )
    if result.get("hosted_collapsed"):
        print("  (+{} more below frontier, collapsed)".format(result["hosted_collapsed"]))
    print("")
    print("LOCAL / ollama (open-weight volume risers):")
    for candidate in result.get("local", []):
        print(
            "  {id}\tvendor={vendor}\tvol={vol}\t[ollama-pull? heuristic]".format(
                id=candidate["model_id"],
                vendor=candidate.get("vendor"),
                vol=candidate.get("total_tokens"),
            )
        )
    if result.get("local_remainder"):
        print("  (+{} more, collapsed)".format(result["local_remainder"]))
    print("")
    print("Confirm a line to add a catalog row / propose an ollama pull. Nothing auto-applies.")


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result))
    else:
        _print_human(result)


def main(argv=None, stdin_text=None):
    """Read-only discovery-digest CLI. Never fetches, never writes."""
    parser = argparse.ArgumentParser(description="OpenRouter discovery-digest (read-only, emit-only).")
    parser.add_argument("--rankings", help="path to a list-daily-model-rankings JSON payload")
    parser.add_argument("--benchmarks", help="path to a list-benchmarks JSON payload")
    parser.add_argument("--catalog-dir", dest="catalog_dir", help="directory holding the three catalog files")
    parser.add_argument("--top-n", dest="top_n", type=int, default=DEFAULT_TOP_N, help="local-lane candidate cap")
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON instead of a table")
    arguments = parser.parse_args(argv)

    inputs = load_inputs(arguments.rankings, arguments.benchmarks, stdin_text)
    if inputs is None:
        _emit(unavailable("no rankings/benchmarks input provided"), arguments.as_json)
        return 0
    rankings, benchmarks = inputs
    if not rankings or not rankings.get("data"):
        _emit(unavailable("no rankings data"), arguments.as_json)
        return 0

    catalog_dir = resolve_catalog_dir(arguments.catalog_dir)
    tracked = load_tracked(catalog_dir) if catalog_dir else {}
    digest = build_digest(rankings, benchmarks or {}, tracked, top_n=arguments.top_n)
    _emit(digest, arguments.as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
