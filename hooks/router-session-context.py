#!/usr/bin/env python3
"""Model-router SessionStart context injector.

Emits routing-ACTIVE or routing-DISABLED context depending on the
~/.claude/.router-off sentinel file. When ACTIVE, also appends a passive
one-line model-catalog staleness status — informational only; the refresh
is offered at /ce-plan, never here. Never blocks; a helper failure degrades
silently (the settings.json wrapper adds `2>/dev/null || true`).

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
    except Exception:
        pass

print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
