"""Pure eligibility checks for replaying completed units in bake-offs.

The constraint layer in ``templates/ROUTING_POLICY.md`` is authoritative.
Callers provide unit metadata as a mapping; this module does not mutate it.
"""

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import urlsplit


_CLASSIFIABLE_SHAPES = {
    "impl-from-frozen-spec",
    "bugfix-with-known-repro",
    "mechanical-refactor",
    "ci/dep/test-bulk",
    "batch-extraction (text/json)",
    "pii-batch classification",
    "vision / ocr batch",
    "huge-context sweep",
    "adversarial / second-opinion review",
    'large-context code read / "where is x"',
}
_NEVER_DELEGATE_SHAPES = {
    "architecture",
    "api design",
    "architecture / api design",
    "spec-writing-as-the-work",
    "tiny edit",
    "tiny edits",
    "session-scoped tools",
    "destructive ops",
    "destructive operations",
    "github mutations",
    "verification gate",
    "verification/review gate",
}
_KNOWN_EXECUTORS = {
    "codex-implementer",
    "codex-scout",
    "haiku-scout",
    "llocal",
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_URL_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^\s\"']+", re.IGNORECASE)
_HOST_ARGUMENT_RE = re.compile(
    r"(?<![a-z0-9_])"
    r"(?:--(?:db-)?host(?:name)?|(?:db_)?host)\s*(?:=|\s)\s*"
    r"(?P<host>\[[^\]]+\]|[a-z0-9._-]+)",
    re.IGNORECASE,
)


def _normalized(value):
    return value.strip().lower() if isinstance(value, str) else None


def _is_local_host(host):
    if not host:
        return False
    normalized = host.strip("[]").rstrip(".").lower()
    return normalized in _LOCAL_HOSTS or normalized.endswith(".local")


def _hosts_in_text(text):
    for raw_url in _URL_RE.findall(text):
        try:
            parsed = urlsplit(raw_url)
            host = parsed.hostname
        except ValueError:
            yield ""
            continue
        if host is None and parsed.scheme.lower() in {"file", "sqlite"}:
            continue
        yield host or ""
    for match in _HOST_ARGUMENT_RE.finditer(text):
        yield match.group("host").strip("[]")


def _has_nonlocal_service(text):
    return any(not _is_local_host(host) for host in _hosts_in_text(text))


def _is_config_file(path):
    name = path.name.lower()
    if name.endswith((".example", ".sample", ".template")):
        return False
    return (
        name == ".env"
        or name.endswith(".env")
        or name.startswith(".env.")
        or path.suffix.lower() in {".toml", ".yaml", ".yml"}
    )


def _unit_dir_scan(unit_dir):
    try:
        root = Path(unit_dir)
    except TypeError:
        return "unit_dir is not path-like"
    if not root.is_dir():
        return "unit_dir is not a readable directory"

    walk_errors = []
    try:
        for directory, subdirs, filenames in os.walk(
            root,
            onerror=walk_errors.append,
            followlinks=False,
        ):
            subdirs[:] = [
                name for name in subdirs if name not in {".git", "node_modules"}
            ]
            for filename in filenames:
                path = Path(directory) / filename
                if not _is_config_file(path):
                    continue
                if path.is_symlink():
                    return f"config file {path.name} is a symlink"
                if not path.is_file():
                    return f"config path {path.name} is not a regular file"
                try:
                    contents = path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError:
                    return f"could not read config file {path.name}"
                if _has_nonlocal_service(contents):
                    return f"non-localhost service in {path.name}"
        if walk_errors:
            return "could not scan unit_dir"
    except OSError:
        return "could not scan unit_dir"
    return None


def _is_never_delegate_shape(shape):
    if shape in _NEVER_DELEGATE_SHAPES:
        return True
    markers = (
        "architecture",
        "api design",
        "api-design",
        "spec-writing",
        "spec writing",
        "tiny edit",
        "session-scoped",
        "mcp",
        "browser",
        "password-manager",
        "secret",
        "destructive",
        "github mutation",
        "verification gate",
        "verification/review gate",
        "review gate",
    )
    return bool(shape and any(marker in shape for marker in markers))


def check_bakeoff_eligibility(unit):
    """Return ``(eligible, reason)`` for a unit descriptor mapping.

    Required keys are ``executor``, ``verify_command``, ``pii_bound``, and
    ``shape``. ``unit_dir`` is optional; when supplied, its credential-bearing
    config files are scanned using the ROUTING_POLICY §1 host rule.
    """

    if not isinstance(unit, Mapping):
        return False, "deny-by-default: unit descriptor is not a mapping"

    executor = _normalized(unit.get("executor"))
    shape = _normalized(unit.get("shape"))
    if executor == "coordinator" or _is_never_delegate_shape(shape):
        return False, "never-delegate: coordinator-only unit"

    if not executor or (
        executor not in _KNOWN_EXECUTORS
        and not executor.startswith("llocal:")
    ):
        return False, "deny-by-default: unclassifiable executor"
    if not shape or shape not in _CLASSIFIABLE_SHAPES:
        return False, "deny-by-default: unclassifiable task shape"
    if not isinstance(unit.get("pii_bound"), bool):
        return False, "deny-by-default: pii_bound must be boolean"

    verify_command = unit.get("verify_command")
    if verify_command is None or (
        isinstance(verify_command, str) and not verify_command.strip()
    ):
        return False, "verify-gate: no load-bearing verify command"
    if not isinstance(verify_command, str):
        return False, "deny-by-default: verify_command must be text"
    if _has_nonlocal_service(verify_command):
        return (
            False,
            "verify-command-live-service: non-localhost service dependency",
        )

    if unit.get("unit_dir") is not None:
        scan_reason = _unit_dir_scan(unit["unit_dir"])
        if scan_reason:
            return False, f"unit-dir-host-scan: {scan_reason}"

    return True, "eligible: constraint-clean unit with load-bearing verification"


def _is_codex_cloud(executor):
    normalized = _normalized(executor)
    return bool(
        normalized
        and normalized.startswith(("codex cloud exec", "codex-cloud-exec"))
    )


def _is_local_challenger(executor):
    normalized = _normalized(executor)
    return bool(
        normalized
        and (normalized == "llocal" or normalized.startswith("llocal:"))
    )


def filter_eligible_challengers(unit, candidate_executors):
    """Return replay-eligible candidates in their original order.

    ``codex cloud exec`` is always removed. For PII-bound units, only local
    model candidates remain. An ineligible unit has no eligible challengers.
    """

    eligible, _reason = check_bakeoff_eligibility(unit)
    if (
        not eligible
        or isinstance(candidate_executors, (str, bytes))
        or not isinstance(candidate_executors, Iterable)
    ):
        return []

    candidates = [
        executor
        for executor in candidate_executors
        if isinstance(executor, str) and not _is_codex_cloud(executor)
    ]
    if unit["pii_bound"]:
        candidates = [
            executor for executor in candidates if _is_local_challenger(executor)
        ]
    return candidates
