"""Compute staleness information for model catalog markdown files."""

import argparse
import datetime
import json
import os
import re
import sys


DEFAULT_STALENESS_DAYS = 30
CATALOG_FILENAMES = [
    "LOCAL_MODELS.md",
    "CODEX_MODELS.md",
    "ANTHROPIC_MODELS.md",
]

_BARE_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def parse_frontmatter(text: str) -> dict:
    """Return key/value strings from a leading delimited frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            closing_index = index
            break
    if closing_index is None:
        return {}

    values = {}
    for line in lines[1:closing_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def catalog_state(path, today=None, default_days=DEFAULT_STALENESS_DAYS) -> dict:
    """Return the fresh, stale, or uninitialized state of one catalog."""
    if today is None:
        today = datetime.date.today()

    frontmatter = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as catalog:
            frontmatter = parse_frontmatter(catalog.read())
    except (OSError, UnicodeError):
        pass

    raw_last_refreshed = frontmatter.get("last_refreshed")
    raw_staleness_days = frontmatter.get("staleness_days")
    try:
        staleness_days = int(raw_staleness_days)
    except (TypeError, ValueError):
        staleness_days = default_days

    refreshed_date = None
    if raw_last_refreshed is not None and _BARE_DATE_RE.fullmatch(
        raw_last_refreshed
    ):
        try:
            refreshed_date = datetime.date.fromisoformat(raw_last_refreshed)
        except ValueError:
            pass

    name = os.path.basename(path)
    if refreshed_date is None:
        return {
            "name": name,
            "path": path,
            "state": "uninitialized",
            "last_refreshed": raw_last_refreshed,
            "staleness_days": staleness_days,
            "age_days": None,
            "line": "{}: not yet initialized — run setup".format(name),
        }

    age_days = (today - refreshed_date).days
    state = "stale" if age_days > staleness_days else "fresh"
    line = None
    if state == "stale":
        line = (
            "{}: stale — last refreshed {}d ago (threshold {}d)".format(
                name, age_days, staleness_days
            )
        )
    return {
        "name": name,
        "path": path,
        "state": state,
        "last_refreshed": raw_last_refreshed,
        "staleness_days": staleness_days,
        "age_days": age_days,
        "line": line,
    }


def check_catalogs(
    base_dir=None,
    today=None,
    names=CATALOG_FILENAMES,
    default_days=DEFAULT_STALENESS_DAYS,
) -> list:
    """Return catalog states for the requested names under a base directory."""
    if base_dir is None:
        base_dir = os.environ.get("MODELS_DIR")
        if base_dir is None:
            here = os.path.dirname(os.path.abspath(__file__))
            sibling = os.path.abspath(os.path.join(here, "..", "templates"))
            # Flat install (~/.claude): catalogs sit beside the helper. Repo layout:
            # helper in bin/, catalogs in the sibling templates/. Prefer whichever
            # actually holds the catalogs so `python3 bin/model_staleness.py` works
            # from a fresh clone without --dir.
            if (not any(os.path.exists(os.path.join(here, n)) for n in names)
                    and os.path.isdir(sibling)
                    and any(os.path.exists(os.path.join(sibling, n)) for n in names)):
                base_dir = sibling
            else:
                base_dir = here
    return [
        catalog_state(
            os.path.join(base_dir, name),
            today=today,
            default_days=default_days,
        )
        for name in names
    ]


_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "none")


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except (OSError, UnicodeError):
        return None


def _default_base_dir():
    base = os.environ.get("MODELS_DIR")
    if base:
        return base
    return os.path.dirname(os.path.abspath(__file__))


def _parse_config_pin(text):
    """Live pin (model/effort) plus the header comment's stated model/effort."""
    out = {"model": None, "effort": None, "comment_model": None, "comment_effort": None}
    if not text:
        return out
    m = re.search(r'(?m)^\s*model\s*=\s*"([^"]+)"', text)
    if m:
        out["model"] = m.group(1)
    m = re.search(r'(?m)^\s*model_reasoning_effort\s*=\s*"([^"]+)"', text)
    if m:
        out["effort"] = m.group(1)
    comment = "\n".join(ln for ln in text.splitlines() if ln.lstrip().startswith("#"))
    cm = re.search(r"\bmodel\s+(gpt[\w.\-]*)", comment)
    if cm:
        out["comment_model"] = cm.group(1)
    ce = re.search(r"\beffort\s+(" + "|".join(_EFFORTS) + r")\b", comment)
    if ce:
        out["comment_effort"] = ce.group(1)
    return out


def _parse_dispatch_docstring(text):
    # The live codex-dispatch doc-string says "currently `X`, effort `Y`"; the
    # public route-sheet template says "e.g. `X`, effort `Y`". Match either and
    # capture the prefix so the proposed fix preserves the file's own wording.
    out = {"model": None, "effort": None, "prefix": None}
    if not text:
        return out
    m = re.search(r"\b(currently|e\.g\.)\s+`([^`]+)`,\s*effort\s+`([^`]+)`", text)
    if m:
        out["prefix"] = m.group(1)
        out["model"] = m.group(2)
        out["effort"] = m.group(3)
    return out


def _catalog_section(text, heading_needle):
    """Body of the '## ...<heading_needle>...' section, up to the next '## '."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and heading_needle.lower() in ln.lower():
            start = i + 1
            break
    if start is None:
        return ""
    body = []
    for ln in lines[start:]:
        if ln.startswith("## "):
            break
        body.append(ln)
    return "\n".join(body)


def _parse_codex_catalog(text):
    out = {"factual_tiers": [], "record_model": None, "record_effort": None,
           "cost_speed_complete": False}
    if not text:
        return out
    pin_sec = _catalog_section(text, "Current pin")
    m = re.search(r"\*\*Model:\*\*\s*`([^`]+)`", pin_sec)
    if m:
        out["record_model"] = m.group(1)
    m = re.search(r"\*\*Reasoning effort:\*\*\s*`([^`]+)`", pin_sec)
    if m:
        out["record_effort"] = m.group(1)
    fac = _catalog_section(text, "Factual")
    out["factual_tiers"] = re.findall(r"`(gpt-[\w.\-]+)`", fac)
    complete = True
    saw_row = False
    for ln in fac.splitlines():
        s = ln.strip()
        if s.startswith("| **"):
            saw_row = True
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not cells or not cells[-1]:
                complete = False
    out["cost_speed_complete"] = complete and saw_row
    return out


def _default_codex_paths():
    base = _default_base_dir()
    return (
        os.path.expanduser("~/.codex/config.toml"),
        os.path.join(base, "skills", "codex-dispatch", "SKILL.md"),
        os.path.join(base, "CODEX_MODELS.md"),
    )


def codex_drift(config_path=None, skill_path=None, catalog_path=None):
    """Detect Codex pin drift. Reports + proposes edits; NEVER writes a file.

    Compares config.toml's live pin, its header comment, the codex-dispatch
    doc-string, and CODEX_MODELS.md's 'Current pin' record. Proposed edits align
    the comment / doc-string / record TO the live pin (never rewriting the live
    `model`/`effort` values). A live-pin rewrite is only *offered* — never auto-
    proposed — and only when the catalog's FACTUAL tier set no longer contains
    the pinned model (never from the unverified best-for-coding note).
    """
    dc, ds, dcat = _default_codex_paths()
    config_path = config_path or dc
    skill_path = skill_path or ds
    catalog_path = catalog_path or dcat

    report = {
        "status": "ok",
        "live_pin": {"model": None, "effort": None},
        "pin_in_factual_tiers": False,
        "factual_tiers": [],
        "disagreements": [],
        "proposed_edits": [],
        "pin_rewrite_offered": False,
        "cost_speed_complete": False,
        "errors": [],
    }

    pin = _parse_config_pin(_read_text(config_path))
    report["live_pin"] = {"model": pin["model"], "effort": pin["effort"]}
    if not pin["model"] or not pin["effort"]:
        report["status"] = "parse_error"
        report["errors"].append("config.toml: could not parse live model/effort pin")
        return report

    doc = _parse_dispatch_docstring(_read_text(skill_path))
    cat = _parse_codex_catalog(_read_text(catalog_path))
    report["factual_tiers"] = cat["factual_tiers"]
    report["cost_speed_complete"] = cat["cost_speed_complete"]
    report["pin_in_factual_tiers"] = pin["model"] in cat["factual_tiers"]

    prov = "live config.toml pin (model=%s, effort=%s)" % (pin["model"], pin["effort"])

    def flag(where, field, found, expected, path, old, new):
        report["disagreements"].append(
            {"where": where, "field": field, "found": found, "expected": expected})
        report["proposed_edits"].append(
            {"file": path, "old": old, "new": new, "provenance": prov})

    if pin["comment_model"] and pin["comment_model"] != pin["model"]:
        flag("config-comment", "model", pin["comment_model"], pin["model"],
             config_path, "model %s" % pin["comment_model"], "model %s" % pin["model"])
    if pin["comment_effort"] and pin["comment_effort"] != pin["effort"]:
        flag("config-comment", "effort", pin["comment_effort"], pin["effort"],
             config_path, "effort %s" % pin["comment_effort"], "effort %s" % pin["effort"])

    if doc["model"] and doc["effort"] and (doc["model"] != pin["model"] or doc["effort"] != pin["effort"]):
        pfx = doc["prefix"]
        flag("dispatch-docstring", "model+effort",
             "%s/%s" % (doc["model"], doc["effort"]),
             "%s/%s" % (pin["model"], pin["effort"]), skill_path,
             "%s `%s`, effort `%s`" % (pfx, doc["model"], doc["effort"]),
             "%s `%s`, effort `%s`" % (pfx, pin["model"], pin["effort"]))

    if cat["record_model"] and cat["record_model"] != pin["model"]:
        flag("catalog-record", "model", cat["record_model"], pin["model"], catalog_path,
             "**Model:** `%s`" % cat["record_model"], "**Model:** `%s`" % pin["model"])
    if cat["record_effort"] and cat["record_effort"] != pin["effort"]:
        flag("catalog-record", "effort", cat["record_effort"], pin["effort"], catalog_path,
             "**Reasoning effort:** `%s`" % cat["record_effort"],
             "**Reasoning effort:** `%s`" % pin["effort"])

    # factual field changed → pinned model no longer a listed tier → OFFER a pin
    # rewrite (which tier is a best-for-coding judgment, never auto-picked here).
    if cat["factual_tiers"] and not report["pin_in_factual_tiers"]:
        report["pin_rewrite_offered"] = True

    if report["disagreements"] or report["pin_rewrite_offered"] or not cat["cost_speed_complete"]:
        report["status"] = "drift"
    return report


def _codex_drift_cli(argv):
    as_json = False
    paths = {"--config": None, "--skill": None, "--catalog": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a in paths:
            i += 1
            paths[a] = argv[i] if i < len(argv) else None
        i += 1
    report = codex_drift(config_path=paths["--config"], skill_path=paths["--skill"],
                         catalog_path=paths["--catalog"])
    if as_json:
        sys.stdout.write(json.dumps(report) + "\n")
    elif report["status"] == "ok":
        sys.stdout.write("Codex pin / comment / doc-string agree; no drift.\n")
    elif report["status"] == "parse_error":
        sys.stdout.write("codex-drift: parse error — %s\n" % "; ".join(report["errors"]))
    else:
        sys.stdout.write("Codex drift detected (offer — nothing written):\n")
        for d in report["disagreements"]:
            sys.stdout.write("  - %s %s: found %r, expected %r\n"
                             % (d["where"], d["field"], d.get("found"), d["expected"]))
        for e in report["proposed_edits"]:
            sys.stdout.write("    fix %s: %r -> %r  [%s]\n"
                             % (os.path.basename(e["file"]), e["old"], e["new"], e["provenance"]))
        if report["pin_rewrite_offered"]:
            sys.stdout.write("  - live pin %s not in factual tiers %s — pin rewrite offered "
                             "(pick a tier; best-for-coding is a judgment)\n"
                             % (report["live_pin"]["model"], report["factual_tiers"]))
    return 0


_OLLAMA_TAG_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(?::[a-z0-9._-]+)?\Z")


def _default_local_catalog():
    """Path to LOCAL_MODELS.md across the repo (templates/) and flat/live layouts."""
    base = os.environ.get("MODELS_DIR")
    if base:
        return os.path.join(base, "LOCAL_MODELS.md")
    here = os.path.dirname(os.path.abspath(__file__))
    sibling = os.path.abspath(os.path.join(here, "..", "templates"))
    for directory in (here, sibling):
        candidate = os.path.join(directory, "LOCAL_MODELS.md")
        if os.path.exists(candidate):
            return candidate
    return os.path.join(here, "LOCAL_MODELS.md")


def _looks_like_ollama_tag(token):
    """A first-cell token is an Ollama model id, not a flag/path/prose token."""
    return bool(token) and bool(_OLLAMA_TAG_RE.fullmatch(token))


def _parse_listed_local_models(text):
    """Model ids from the 'Local Model Inventory' table's first column only.

    Keys on the first cell so backticked flags/paths in other cells
    (`--workers`, `--num-predict`, `/api/chat`) are never mistaken for models,
    and the separate 'Candidate Models' section is excluded by construction.
    """
    section = _catalog_section(text, "Local Model Inventory")
    listed = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        first = stripped.strip("|").split("|", 1)[0].strip()
        match = re.fullmatch(r"`([^`]+)`", first)
        if not match:
            continue
        token = match.group(1).strip()
        if _looks_like_ollama_tag(token) and token not in listed:
            listed.append(token)
    return listed


def _normalize_ollama_tag(tag):
    """Reconcile the one naming difference between the table and `ollama list`:
    an implicit vs explicit `:latest`. Verified against real `ollama list` output
    — Ollama tags and catalog rows otherwise share the same namespace, so no
    version-reordering key (see openrouter naming-reconciliation) is needed here.
    """
    tag = tag.strip().lower()
    if ":" not in tag:
        tag = tag + ":latest"
    return tag


def _fetch_installed_models(host=None, timeout=5):
    """Live installed model ids from Ollama's GET /api/tags."""
    import urllib.request

    base = host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if not base.startswith("http"):
        base = "http://" + base
    url = base.rstrip("/") + "/api/tags"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [m["name"] for m in data.get("models", []) if m.get("name")]


def local_drift(catalog_path=None, installed=None, host=None, timeout=5):
    """Detect drift between LOCAL_MODELS.md's installed inventory table and the
    models actually installed in Ollama. Reports + proposes; NEVER writes.

    `installed` is the live list of installed model ids (e.g. `llocal models
    --names` / GET /api/tags); when None it is fetched live. Matching normalizes
    an implicit/explicit `:latest`. Two drift directions are surfaced:
    `missing_from_table` (pulled but undocumented → propose an add-row) and
    `stale_in_table` (documented but no longer installed → propose verify/drop).
    """
    catalog_path = catalog_path or _default_local_catalog()
    report = {
        "status": "ok",
        "installed": [],
        "listed": [],
        "missing_from_table": [],
        "stale_in_table": [],
        "proposed_edits": [],
        "errors": [],
    }

    text = _read_text(catalog_path)
    if text is None:
        report["status"] = "parse_error"
        report["errors"].append(
            "LOCAL_MODELS.md: could not read %s" % catalog_path)
        return report

    listed = _parse_listed_local_models(text)
    report["listed"] = listed

    if installed is None:
        try:
            installed = _fetch_installed_models(host=host, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - network/parse must not crash
            report["status"] = "parse_error"
            report["errors"].append(
                "could not fetch installed models: %r" % exc)
            return report
    report["installed"] = list(installed)

    listed_by_key = {_normalize_ollama_tag(t): t for t in listed}
    installed_by_key = {_normalize_ollama_tag(t): t for t in installed}

    for key, original in installed_by_key.items():
        if key not in listed_by_key:
            report["missing_from_table"].append(original)
            report["proposed_edits"].append({
                "file": catalog_path,
                "action": "add-row",
                "model": original,
                "note": ("installed in Ollama but absent from the inventory "
                         "table — add a row (Best for / Avoid / Size) and bump "
                         "last_reconciled"),
            })

    for key, original in listed_by_key.items():
        if key not in installed_by_key:
            report["stale_in_table"].append(original)
            report["proposed_edits"].append({
                "file": catalog_path,
                "action": "flag-stale",
                "model": original,
                "note": ("listed in the inventory table but not installed — "
                         "verify it was removed, then drop the row or re-pull"),
            })

    if report["missing_from_table"] or report["stale_in_table"]:
        report["status"] = "drift"
    return report


def _local_drift_cli(argv):
    as_json = False
    catalog_path = None
    host = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--catalog":
            i += 1
            catalog_path = argv[i] if i < len(argv) else None
        elif a == "--host":
            i += 1
            host = argv[i] if i < len(argv) else None
        i += 1
    report = local_drift(catalog_path=catalog_path, host=host)
    if as_json:
        sys.stdout.write(json.dumps(report) + "\n")
    elif report["status"] == "ok":
        sys.stdout.write(
            "Installed models and LOCAL_MODELS.md inventory agree; no drift.\n")
    elif report["status"] == "parse_error":
        sys.stdout.write("local-drift: %s\n" % "; ".join(report["errors"]))
    else:
        sys.stdout.write("Local model drift detected (offer — nothing written):\n")
        for m in report["missing_from_table"]:
            sys.stdout.write("  - installed but not in table: %s "
                             "(add a row, bump last_reconciled)\n" % m)
        for m in report["stale_in_table"]:
            sys.stdout.write("  - in table but not installed: %s "
                             "(verify removed; drop row or re-pull)\n" % m)
    return 0


def main(argv=None):
    """Run the model catalog staleness command-line interface."""
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "codex-drift":
        return _codex_drift_cli(argv[1:])
    if argv and argv[0] == "local-drift":
        return _local_drift_cli(argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--dir", dest="base_dir")
    parser.add_argument("files", nargs="*")
    arguments = parser.parse_args(argv)

    if arguments.files:
        results = [catalog_state(path) for path in arguments.files]
    else:
        results = check_catalogs(base_dir=arguments.base_dir)

    if arguments.as_json:
        print(json.dumps(results))
    else:
        for result in results:
            if result["line"] is not None:
                print(result["line"])


if __name__ == "__main__":
    main()
