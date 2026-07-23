#!/usr/bin/env python3
"""Append and query the router's field-record JSONL ledger.

Importable usage:
    append_record(record, path)
    result = query_records(path, shape="stdlib-python", date_from="2026-01-01")
    result.records
    result.skipped_count

The default ledger is ~/.claude/router-field-records.jsonl. Pass ``path``
explicitly for tests, fixtures, and alternate ledgers.

Also the shared home for the replay-bundle capture protocol (U2):
    parse_outcome_line(line)      -> ParsedOutcome (tolerant of a trailing base: token)
    scan_bundle_content(texts)   -> list of structural-secret hits
    write_bundle(root, unit_ref, ...) -> BundleResult
"""

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Sequence


DEFAULT_LEDGER_PATH = Path("~/.claude/router-field-records.jsonl").expanduser()
KINDS = frozenset({"replay", "real", "reverse-replay"})
REQUIRED_FIELDS = (
    "unit_ref",
    "shape",
    "executor",
    "kind",
    "verify_pass",
    "fix_rounds",
    "base_commit",
    "provenance",
    "date",
)
STRING_FIELDS = ("unit_ref", "shape", "executor", "base_commit", "date")
OPTIONAL_PROVENANCE_FIELDS = (
    "quantization",
    "judge_model",
    "rubric_version",
)


class QueryResult(NamedTuple):
    """Records returned by a query and the number of corrupt lines skipped."""

    records: list[dict[str, Any]]
    skipped_count: int


def validate_record(record: Mapping[str, Any]) -> None:
    """Raise ValueError when a record does not match the append grammar."""
    if not isinstance(record, Mapping):
        raise ValueError("record must be a JSON object")

    for field in REQUIRED_FIELDS:
        if field not in record:
            raise ValueError(f"missing required field: {field}")

    for field in STRING_FIELDS:
        if not isinstance(record[field], str):
            raise ValueError(f"{field} must be a string")

    if record["kind"] not in KINDS:
        choices = ", ".join(sorted(KINDS))
        raise ValueError(f"kind must be one of: {choices}")
    if not isinstance(record["verify_pass"], bool):
        raise ValueError("verify_pass must be a bool")
    if isinstance(record["fix_rounds"], bool) or not isinstance(
        record["fix_rounds"], int
    ):
        raise ValueError("fix_rounds must be an int")

    provenance = record["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a JSON object")
    if "model_tag" not in provenance:
        raise ValueError("missing required field: provenance.model_tag")
    if not isinstance(provenance["model_tag"], str):
        raise ValueError("provenance.model_tag must be a string")
    for field in OPTIONAL_PROVENANCE_FIELDS:
        if field in provenance and not isinstance(provenance[field], str):
            raise ValueError(f"provenance.{field} must be a string")

    if "margin" in record:
        margin = record["margin"]
        if (
            isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not -1.0 <= margin <= 1.0
        ):
            raise ValueError("margin must be between -1.0 and 1.0")


def append_record(
    record: Mapping[str, Any],
    path: str | Path = DEFAULT_LEDGER_PATH,
) -> None:
    """Validate and append one compact, newline-terminated JSON object."""
    validate_record(record)
    ledger_path = Path(path).expanduser()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        dict(record),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(encoded + "\n")


def query_records(
    path: str | Path = DEFAULT_LEDGER_PATH,
    *,
    shape: str | None = None,
    executor: str | None = None,
    kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> QueryResult:
    """Read records matching exact filters and an inclusive date window."""
    ledger_path = Path(path).expanduser()
    if not ledger_path.exists():
        return QueryResult(records=[], skipped_count=0)

    records = []
    skipped_count = 0
    with ledger_path.open(encoding="utf-8") as ledger:
        for line in ledger:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                skipped_count += 1
                continue
            if not isinstance(record, dict):
                skipped_count += 1
                continue
            if shape is not None and record.get("shape") != shape:
                continue
            if executor is not None and record.get("executor") != executor:
                continue
            if kind is not None and record.get("kind") != kind:
                continue
            record_date = record.get("date")
            if date_from is not None and (
                not isinstance(record_date, str) or record_date < date_from
            ):
                continue
            if date_to is not None and (
                not isinstance(record_date, str) or record_date > date_to
            ):
                continue
            records.append(record)

    return QueryResult(records=records, skipped_count=skipped_count)


# --- Replay-bundle capture protocol (U2) ------------------------------------
#
# The §6 outcome line gains an OPTIONAL, labelled trailing `base:<sha>` token.
# It is located by its `base:` label, not by position, so a reader that indexes
# the first seven `·`-delimited fields keeps working unchanged.

OUTCOME_DELIM = " · "
_BASE_TOKEN = re.compile(r"^base:(?P<sha>\S+)$")


class ParsedOutcome(NamedTuple):
    """A §6 outcome line split into the fields the flywheel joins on."""

    unit_ref: str | None
    executor: str | None
    status: str | None
    date: str | None
    base_commit: str | None
    fields: list[str]


def parse_outcome_line(line: str) -> ParsedOutcome:
    """Parse a §6 outcome line, tolerating a trailing ``base:<sha>`` token.

    Lines written before U2 (seven fields, no base token) parse cleanly with
    ``base_commit is None``; lines carrying the token expose it regardless of
    where it sits among the trailing fields.
    """
    stripped = line.strip().lstrip("-").strip()
    fields = [f.strip() for f in stripped.split(OUTCOME_DELIM) if f.strip()]

    base_commit = None
    positional = []
    for field in fields:
        match = _BASE_TOKEN.match(field)
        if match:
            base_commit = match.group("sha")
        else:
            positional.append(field)

    def at(index: int) -> str | None:
        return positional[index] if index < len(positional) else None

    return ParsedOutcome(
        unit_ref=at(0),
        executor=at(1),
        status=at(2),
        date=at(6),
        base_commit=base_commit,
        fields=fields,
    )


# Structural secret patterns mirroring scripts/leak-check.sh's structural
# checks. leak-check.sh also enforces a gitignored term blocklist against
# tracked files; that repo-file scan stays the U11 push-time gate. Bundle
# content is in-hand text, so only the structural patterns apply here.
_SECRET_PATTERNS = (
    ("absolute home path", re.compile(r"/Users/[a-z]|/home/[a-z]")),
    (
        "credential-shaped URL",
        re.compile(r"[a-z]+://[^ /:]+:[^ /@]+@[a-zA-Z0-9.-]+"),
    ),
    (
        "UUID-shaped id",
        re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        ),
    ),
)


def scan_bundle_content(texts: Iterable[str]) -> list[str]:
    """Return one hit string per structural-secret match across ``texts``."""
    hits = []
    for text in texts:
        if text is None:
            continue
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{label}: matched in bundle content")
    return hits


class BundleResult(NamedTuple):
    """Outcome of a bundle write."""

    written: bool
    path: Path | None
    margin_limited: bool
    refused_reason: str | None


_BUNDLE_KEY_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_.-]*$")


def write_bundle(
    root: str | Path,
    unit_ref: str,
    *,
    base_commit: str,
    spec: str,
    verify_commands: Sequence[str],
    first_shot_patch: str | None = None,
    namespace: str | None = None,
) -> BundleResult:
    """Write a replay bundle for ``unit_ref`` under ``root``.

    Layout::

        <root>/[<namespace>/]<unit_ref>/meta.json   base_commit, verify_commands, margin_limited
        <root>/[<namespace>/]<unit_ref>/spec.md      frozen spec
        <root>/[<namespace>/]<unit_ref>/first_shot.patch   incumbent's first diff (when present)

    ``unit_ref`` alone is NOT unique — nearly every plan has a ``U1`` — so a
    ``namespace`` (a plan/repo-unique key) SHOULD be passed to keep bundles from
    colliding across plans. Both ``namespace`` and ``unit_ref`` are validated as
    single safe path components (no traversal); a value that would escape ``root``
    refuses the write.

    A missing first-shot artifact does NOT reject the bundle: it is marked
    ``margin_limited`` (U4 degrades to verify-only grading), and any stale
    ``first_shot.patch`` from a prior capture is removed so the runner never grades
    against a wrong incumbent. A structural-secret hit in any bundle content
    REFUSES the write and reports the reason; nothing is written.
    """
    for component in ([namespace] if namespace is not None else []) + [unit_ref]:
        if not _BUNDLE_KEY_RE.match(component or ""):
            return BundleResult(
                written=False,
                path=None,
                margin_limited=False,
                refused_reason=f"unsafe bundle path component: {component!r}",
            )

    hits = scan_bundle_content(
        [spec, first_shot_patch, *verify_commands]
    )
    if hits:
        return BundleResult(
            written=False,
            path=None,
            margin_limited=False,
            refused_reason="; ".join(hits),
        )

    margin_limited = first_shot_patch is None
    root_dir = Path(root).expanduser()
    bundle_dir = root_dir / namespace / unit_ref if namespace else root_dir / unit_ref
    bundle_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "unit_ref": unit_ref,
        "namespace": namespace,
        "base_commit": base_commit,
        "verify_commands": list(verify_commands),
        "margin_limited": margin_limited,
    }
    (bundle_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "spec.md").write_text(spec, encoding="utf-8")
    patch_path = bundle_dir / "first_shot.patch"
    if first_shot_patch is not None:
        patch_path.write_text(first_shot_patch, encoding="utf-8")
    else:
        patch_path.unlink(missing_ok=True)

    return BundleResult(
        written=True,
        path=bundle_dir,
        margin_limited=margin_limited,
        refused_reason=None,
    )
