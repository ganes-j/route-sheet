#!/usr/bin/env python3
"""Append and query the router's field-record JSONL ledger.

Importable usage:
    append_record(record, path)
    result = query_records(path, shape="stdlib-python", date_from="2026-01-01")
    result.records
    result.skipped_count

The default ledger is ~/.claude/router-field-records.jsonl. Pass ``path``
explicitly for tests, fixtures, and alternate ledgers.
"""

import json
from pathlib import Path
from typing import Any, Mapping, NamedTuple


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
