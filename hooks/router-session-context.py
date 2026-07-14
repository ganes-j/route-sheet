#!/usr/bin/env python3
"""Model-router SessionStart context injector.

Emits routing-ACTIVE or routing-DISABLED context depending on the
~/.claude/.router-off sentinel file. Wired in via a SessionStart hook in
settings.json.

REVERT: delete this file AND remove the SessionStart command in
settings.json that calls it (look for router-session-context.py).
SOFT-DISABLE (no revert needed): touch ~/.claude/.router-off
"""
import json
import os

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
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}))
