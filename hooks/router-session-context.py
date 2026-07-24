#!/usr/bin/env python3
"""Model-router SessionStart context injector.

Emits routing-ACTIVE or routing-DISABLED context depending on the
~/.claude/.router-off sentinel file. When ACTIVE, also appends a passive
one-line model-catalog staleness status and BAKE-OFF activity digest —
informational only; the refresh is offered at /ce-plan, never here. Never
blocks; a helper failure degrades silently (the settings.json wrapper adds
`2>/dev/null || true`).

REVERT: delete this file AND remove the SessionStart command in
settings.json that calls it (look for router-session-context.py).
SOFT-DISABLE (no revert needed): touch ~/.claude/.router-off
PLUGIN INSTALL: dormant until the `enable_session_status` option is enabled
(Claude Code exports it as CLAUDE_PLUGIN_OPTION_ENABLE_SESSION_STATUS); the
live ~/.claude copy is wired via settings.json and has no such gate.
"""
import json
import os
import sys


def bakeoff_digest_line(ledger_path=None, state_path=None):
    """Return the passive bake-off digest and advance its line-count marker."""
    ledger_path = ledger_path or os.path.expanduser(
        "~/.claude/router-field-records.jsonl"
    )
    state_path = state_path or os.path.expanduser(
        "~/.claude/.bakeoff-digest-state"
    )

    total = 0
    wins = 0
    ledger_ok = True
    try:
        with open(ledger_path, "r", encoding="utf-8", errors="replace") as ledger:
            for line in ledger:
                try:
                    record = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                total += 1
                margin = record.get("margin")
                if (
                    isinstance(margin, (int, float))
                    and not isinstance(margin, bool)
                    and margin > 0
                ):
                    wins += 1
    except FileNotFoundError:
        pass  # legitimately empty — safe to advance the marker to 0
    except OSError:
        # Unreadable (permission/IO) → degrade to idle rather than SUPPRESS the
        # digest, but don't trust the count or advance the marker (a transient
        # read error must not reset "seen" and cause a spurious burst next time).
        ledger_ok = False

    seen = 0
    try:
        with open(state_path, "r", encoding="utf-8") as state_file:
            saved_seen = json.load(state_file).get("seen")
        if (
            isinstance(saved_seen, int)
            and not isinstance(saved_seen, bool)
            and saved_seen >= 0
        ):
            seen = saved_seen
    except (AttributeError, OSError, TypeError, ValueError):
        pass

    # Advance the marker best-effort, and only when the ledger was actually read:
    # a write failure must NOT lose the digest line (else a persistently
    # unwritable state dir goes dark forever), and an unreadable ledger must NOT
    # reset "seen". In both cases the marker holds; next session re-reports.
    if ledger_ok:
        try:
            state_dir = os.path.dirname(state_path)
            if state_dir:
                os.makedirs(state_dir, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as state_file:
                json.dump({"seen": total}, state_file)
                state_file.write("\n")
        except OSError:
            pass

    if total == 0:
        return "BAKE-OFF: idle — no field records yet"
    return (
        "BAKE-OFF: %d new record(s) since last check · "
        "%d challenger win(s) pending · %d ledger record(s)"
        % (max(0, total - seen), wins, total)
    )


# Plugin opt-in gate (packaging layer; absent from the live ~/.claude hook).
# Empty stdout = nothing injected. .router-off below still governs
# ACTIVE-vs-DISABLED once opted in.
if os.environ.get("CLAUDE_PLUGIN_OPTION_ENABLE_SESSION_STATUS") != "true":
    sys.exit(0)

sentinel = os.path.expanduser("~/.claude/.router-off")
if os.path.exists(sentinel):
    ctx = (
        "MODEL ROUTER: DISABLED — ~/.claude/.router-off is present. "
        "Ignore the Model Router guidance in CLAUDE.md; do not route or delegate by plan; work inline."
    )
else:
    ctx = (
        "MODEL ROUTER: ACTIVE. When planning multi-unit work via /ce-plan, consult "
        "~/.claude/ROUTING_POLICY.md and run the route-plan skill to write a sidecar routing manifest; "
        "dispatch spec'd units per the manifest (codex-dispatch skill for Codex, llocal for bulk/PII/vision). "
        "The constraint layer (PII-never-Codex, prod-credential block) always wins over task-shape routing. "
        "Disable anytime with: touch ~/.claude/.router-off"
    )
    # Passive model-catalog staleness status — a status line per stale catalog and a
    # "not yet initialized" line per absent one. Never an offer, never blocks; the
    # refresh offer lives at /ce-plan (route-plan). model_staleness.py is resolved
    # relative to this hook's own directory so it works unchanged in the public mirror.
    try:
        hook_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, hook_dir)
        repo_bin = os.path.abspath(os.path.join(hook_dir, "..", "bin"))
        if os.path.isdir(repo_bin):
            sys.path.insert(0, repo_bin)
        import model_staleness

        lines = [s["line"] for s in model_staleness.check_catalogs() if s.get("line")]
        if lines:
            ctx = ctx + (
                "\n\nMODEL CATALOGS (passive status — a refresh is offered at /ce-plan, not here): "
                + " · ".join(lines)
            )
        # Passive installed-vs-listed drift for LOCAL_MODELS.md: warn when a model
        # is pulled but undocumented (or documented but gone). Short timeout so a
        # down Ollama never delays session start; the reconcile is offered at
        # /ce-plan, not here.
        drift = model_staleness.local_drift(timeout=1.5)
        drift_bits = ["%s installed but not in table" % m
                      for m in drift.get("missing_from_table", [])]
        drift_bits += ["%s in table but not installed" % m
                       for m in drift.get("stale_in_table", [])]
        if drift_bits:
            ctx = ctx + (
                "\n\nLOCAL MODEL DRIFT (offer — reconcile the LOCAL_MODELS.md inventory "
                "at /ce-plan, not here): " + " · ".join(drift_bits)
            )
    except Exception:
        pass

    try:
        digest_line = bakeoff_digest_line()
        if digest_line is not None:
            ctx = ctx + "\n\n" + digest_line
    except Exception:
        pass

print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
