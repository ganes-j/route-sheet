#!/usr/bin/env python3
"""Propose sign-off-gated ``❓`` challenger seeds for policy matrix rows.

This helper is deliberately emit-only.  It reads catalog, policy, and optional
ledger snapshots, returns proposal objects, and prints pasteable proposal lines.
It never opens any input for writing and never edits ``ROUTING_POLICY.md``.
"""

import argparse
import datetime
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping

try:
    from bin.openrouter_discovery import (
        CATALOG_LANES,
        canonical_key,
        load_tracked,
        parse_tracked_from_text,
        resolve_catalog_dir,
    )
except ModuleNotFoundError:  # Direct ``python3 bin/challenger_seeding.py`` use.
    from openrouter_discovery import (  # type: ignore[no-redef]
        CATALOG_LANES,
        canonical_key,
        load_tracked,
        parse_tracked_from_text,
        resolve_catalog_dir,
    )


STATES = ("✅", "❌", "❓")
DEFAULT_STALENESS_DAYS = 90
LAST_RE = re.compile(r"\blast\s+(\d{4}-\d{2}-\d{2})\b")
NEW_CATALOG_MODEL = "new-catalog-model"
PLAUSIBLE_UNTESTED = "plausible-untested"
MATERIALLY_CHANGED_RETRY = "materially-changed-retry"
STALE_VERIFIED = "stale-verified"
TRIGGER_PRIORITY = {
    PLAUSIBLE_UNTESTED: 0,
    NEW_CATALOG_MODEL: 1,
    STALE_VERIFIED: 2,
    MATERIALLY_CHANGED_RETRY: 3,
}
BEST_FOR_PHRASES = {
    "batch-extraction": ("extraction", "structured data", "json-schema"),
    "pii-batch classification": ("pii", "private classification"),
    "vision / ocr batch": ("ocr", "image ocr", "batch vision"),
    "mechanical-refactor": ("refactor",),
    "impl-from-frozen-spec": ("code gen", "code-gen", "well-specified"),
    "ci/dep/test-bulk": ("test authoring", "dependency bump", "dep bump"),
    "huge-context sweep": ("huge-context", "huge context sweep"),
    "adversarial / second-opinion review": (
        "adversarial review",
        "second-opinion review",
        "second opinion review",
    ),
    'large-context code read / "where is x"': (
        "large-context code read",
        "where is x",
    ),
}


@dataclass(frozen=True)
class CatalogModel:
    """One already-parsed catalog model and its narrow routing metadata."""

    model_id: str
    task_fit_tags: frozenset[str] = frozenset()
    is_new: bool = False
    new_version_of: str | None = None


@dataclass(frozen=True)
class MatrixCandidate:
    model_id: str
    state: str
    last: datetime.date | None = None


@dataclass(frozen=True)
class ShapeRow:
    shape: str
    candidates: tuple[MatrixCandidate, ...]


@dataclass(frozen=True)
class SeedProposal:
    """A maintainer-reviewable request to add or reopen one ``❓`` cell."""

    target_shape: str
    model_id: str
    trigger: str
    reason: str

    @property
    def paste_line(self) -> str:
        return f"{self.target_shape} | {self.model_id} ❓ | {self.reason}"


def _section_2(text: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and re.match(r"##\s*2\b", line):
            start = index + 1
            break
    if start is None:
        return []
    section = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        section.append(line)
    return section


def _parse_candidates(cell: str) -> tuple[MatrixCandidate, ...]:
    candidates = []
    for raw in cell.split(" · "):
        positions = [(raw.find(state), state) for state in STATES if state in raw]
        if not positions:
            continue
        position, state = min(positions)
        model_id = raw[:position].replace("★", "").strip()
        if not model_id:
            continue
        match = LAST_RE.search(raw[position + 1 :])
        try:
            last = datetime.date.fromisoformat(match.group(1)) if match else None
        except ValueError:
            last = None
        candidates.append(MatrixCandidate(model_id=model_id, state=state, last=last))
    return tuple(candidates)


def parse_candidate_matrix(text: str) -> list[ShapeRow]:
    """Parse §2 rows from policy text without interpreting the notes column."""

    rows = []
    for line in _section_2(text):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        shape = cells[0]
        if shape.lower() == "task shape" or not shape or set(shape) <= set("-: "):
            continue
        rows.append(ShapeRow(shape=shape, candidates=_parse_candidates(cells[1])))
    return rows


def _normalized(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _tag_matches_shape(tag: str, shape: str) -> bool:
    """Narrow v1 match: exact shape, or its explicit parenthesized base tag."""

    tag_value = _normalized(tag)
    shape_value = _normalized(shape)
    if tag_value == shape_value:
        return True
    return (
        shape_value.startswith(tag_value)
        and len(shape_value) > len(tag_value)
        and shape_value[len(tag_value)] in (" ", "(")
    )


def _ledger_index(
    ledger_recency: Mapping[tuple[str, str], datetime.date | str],
) -> dict[tuple[str, str], datetime.date]:
    latest = {}
    for (ledger_shape, ledger_model), value in ledger_recency.items():
        try:
            parsed = (
                value if isinstance(value, datetime.date)
                else datetime.date.fromisoformat(value)
            )
        except (TypeError, ValueError):
            continue
        key = (ledger_shape, canonical_key(ledger_model))
        latest[key] = max(latest.get(key, parsed), parsed)
    return latest


def _indexed_candidate(
    candidates: Mapping[str, MatrixCandidate],
    model_id: str,
) -> MatrixCandidate | None:
    """Canonical match, plus an explicit unversioned local-family alias."""

    exact = candidates.get(canonical_key(model_id))
    if exact is not None or ":" not in model_id:
        return exact
    family = model_id.partition(":")[0]
    alias = candidates.get(canonical_key(family))
    if alias is not None and ":" not in alias.model_id:
        return alias
    return None


def propose_seeds(
    catalogs: Iterable[CatalogModel],
    matrix: Iterable[ShapeRow],
    *,
    today: datetime.date,
    staleness_days: int = DEFAULT_STALENESS_DAYS,
    ledger_recency: Mapping[tuple[str, str], datetime.date | str] | None = None,
) -> list[SeedProposal]:
    """Return deterministic seed proposals; never mutate or write its inputs.

    Existing candidates suppress ordinary new/plausible proposals using
    ``canonical_key``.  The two intentional reopen cases are exceptions:
    a catalog-declared replacement for a ``❌`` version and a ``✅`` whose most
    recent cell/ledger evidence is older than ``staleness_days``.
    """

    if staleness_days < 0:
        raise ValueError("staleness_days must be non-negative")
    rows = tuple(matrix)
    candidate_index = {
        row.shape: {
            canonical_key(candidate.model_id): candidate
            for candidate in row.candidates
        }
        for row in rows
    }
    recency = _ledger_index(ledger_recency or {})
    proposals = {}

    def emit(row: ShapeRow, model_id: str, trigger: str, reason: str) -> None:
        key = (row.shape, canonical_key(model_id))
        current = proposals.get(key)
        if (
            current is None
            or TRIGGER_PRIORITY[trigger] > TRIGGER_PRIORITY[current.trigger]
        ):
            proposals[key] = SeedProposal(row.shape, model_id, trigger, reason)

    for model in catalogs:
        for row in rows:
            row_candidates = candidate_index[row.shape]
            existing = _indexed_candidate(row_candidates, model.model_id)

            if model.new_version_of:
                replaced = _indexed_candidate(row_candidates, model.new_version_of)
                if replaced is not None and replaced.state == "❌" and existing is None:
                    emit(
                        row,
                        model.model_id,
                        MATERIALLY_CHANGED_RETRY,
                        f"new catalog version of ruled-out {replaced.model_id}",
                    )
                    continue

            if existing is not None:
                if existing.state == "✅" and existing.last is not None:
                    ledger_last = recency.get(
                        (row.shape, canonical_key(existing.model_id))
                    )
                    latest = max(existing.last, ledger_last) if ledger_last else existing.last
                    if (today - latest).days > staleness_days:
                        emit(
                            row,
                            existing.model_id,
                            STALE_VERIFIED,
                            f"verified evidence older than {staleness_days} days",
                        )
                continue

            if not any(
                _tag_matches_shape(tag, row.shape) for tag in model.task_fit_tags
            ):
                continue
            if model.is_new:
                emit(
                    row,
                    model.model_id,
                    NEW_CATALOG_MODEL,
                    "new catalog model matches task-fit tag",
                )
            else:
                emit(
                    row,
                    model.model_id,
                    PLAUSIBLE_UNTESTED,
                    "catalog task-fit tag matches row; candidate is untested",
                )

    return list(proposals.values())


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _best_for_tags(best_for: str, known_shapes: Iterable[str]) -> frozenset[str]:
    """Map Best-for prose to rows conservatively; explicit phrases only."""

    prose = _normalized(best_for)
    tags = set()
    for shape in known_shapes:
        normalized_shape = _normalized(shape)
        base = normalized_shape.split(" (", 1)[0]
        phrases = BEST_FOR_PHRASES.get(base, ())
        if normalized_shape in prose or base in prose or any(p in prose for p in phrases):
            tags.add(shape)
    return frozenset(tags)


def parse_catalog_text(
    text: str,
    lane: str,
    *,
    known_shapes: Iterable[str] = (),
) -> list[CatalogModel]:
    """Parse model IDs and narrow Best-for tags from catalog Markdown tables."""

    shapes = tuple(known_shapes)
    models = []
    header = None
    model_indexes = ()
    best_index = None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            header = None
            model_indexes = ()
            best_index = None
            continue
        cells = _table_cells(line)
        lowered = [_normalized(cell.replace("`", "")) for cell in cells]
        if any("best for" in cell for cell in lowered):
            header = lowered
            model_indexes = tuple(
                index for index, name in enumerate(header) if "model" in name
            )
            best_index = next(
                index for index, name in enumerate(header) if "best for" in name
            )
            continue
        if (
            header is None
            or best_index is None
            or len(cells) != len(header)
            or set(cells[0]) <= set("-: ")
        ):
            continue

        if not model_indexes:
            continue
        model_id = None
        for index in model_indexes:
            parsed = parse_tracked_from_text(cells[index], lane)
            if parsed:
                model_id = next(iter(parsed))
                break
        if model_id is None:
            continue
        models.append(
            CatalogModel(
                model_id=model_id,
                task_fit_tags=_best_for_tags(cells[best_index], shapes),
            )
        )
    return models


def _versionless_key(model_id: str) -> str:
    return "|".join(sorted(re.findall(r"[a-z]+", model_id.lower())))


def mark_catalog_changes(
    current: Iterable[CatalogModel],
    previous_model_ids: Iterable[str],
) -> list[CatalogModel]:
    """Annotate current parsed entries by comparison with a prior snapshot."""

    previous = tuple(previous_model_ids)
    previous_keys = {canonical_key(model_id) for model_id in previous}
    previous_by_family = {}
    for model_id in previous:
        previous_by_family.setdefault(_versionless_key(model_id), model_id)
    result = []
    for model in current:
        if canonical_key(model.model_id) in previous_keys:
            result.append(model)
            continue
        prior_version = previous_by_family.get(_versionless_key(model.model_id))
        result.append(replace(model, is_new=True, new_version_of=prior_version))
    return result


def load_ledger_recency(path: str | Path) -> dict[tuple[str, str], datetime.date]:
    """Read latest shape/model dates from the optional field-record JSONL."""

    latest = {}
    try:
        ledger = Path(path).open(encoding="utf-8")
    except OSError:
        return latest
    with ledger:
        for line in ledger:
            try:
                record = json.loads(line)
                shape = record["shape"]
                model_id = (
                    record.get("provenance", {}).get("model_tag")
                    or record.get("executor", "").removeprefix("llocal:")
                )
                record_date = datetime.date.fromisoformat(record["date"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if not shape or not model_id:
                continue
            key = (shape, model_id)
            latest[key] = max(latest.get(key, record_date), record_date)
    return latest


def _load_catalogs(
    catalog_dir: str | Path,
    shapes: Iterable[str],
) -> list[CatalogModel]:
    shapes = tuple(shapes)
    models = []
    for filename, lane in CATALOG_LANES:
        try:
            text = (Path(catalog_dir) / filename).read_text(encoding="utf-8")
        except OSError:
            continue
        models.extend(parse_catalog_text(text, lane, known_shapes=shapes))
    return models


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit-only challenger seed proposals; never edits policy files."
    )
    parser.add_argument("--catalog-dir", help="current model-catalog directory")
    parser.add_argument(
        "--previous-catalog-dir",
        help="optional prior catalog snapshot used to identify new versions",
    )
    parser.add_argument("--policy", help="ROUTING_POLICY.md path")
    parser.add_argument("--ledger", help="optional field-record JSONL path")
    parser.add_argument("--today", help="YYYY-MM-DD (defaults to the CLI run date)")
    parser.add_argument(
        "--staleness-days", type=int, default=DEFAULT_STALENESS_DAYS
    )
    arguments = parser.parse_args(argv)

    catalog_dir = resolve_catalog_dir(arguments.catalog_dir)
    if catalog_dir is None:
        parser.error("catalog directory not found")
    policy_path = Path(arguments.policy) if arguments.policy else (
        Path(catalog_dir) / "ROUTING_POLICY.md"
    )
    try:
        policy_text = policy_path.read_text(encoding="utf-8")
    except OSError as error:
        parser.error(f"cannot read policy: {error}")
    try:
        today = (
            datetime.date.fromisoformat(arguments.today)
            if arguments.today
            else datetime.date.today()
        )
    except ValueError:
        parser.error("--today must be YYYY-MM-DD")

    rows = parse_candidate_matrix(policy_text)
    models = _load_catalogs(catalog_dir, (row.shape for row in rows))
    if arguments.previous_catalog_dir:
        previous = load_tracked(arguments.previous_catalog_dir)
        models = mark_catalog_changes(models, previous)
    ledger = load_ledger_recency(arguments.ledger) if arguments.ledger else {}
    proposals = propose_seeds(
        models,
        rows,
        today=today,
        staleness_days=arguments.staleness_days,
        ledger_recency=ledger,
    )

    print("Challenger seed proposals (maintainer sign-off required).")
    print("Nothing is written. Paste/approve only the lines you accept.")
    for proposal in proposals:
        print(proposal.paste_line)
    if not proposals:
        print("(no proposals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
