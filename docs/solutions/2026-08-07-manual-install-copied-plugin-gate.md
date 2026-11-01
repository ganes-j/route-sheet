# A manual install copied the plugin-only hook gate, so the hook was silently mute

**Area:** `SETUP.md` (Tier 1 copy list, Phase 3, check 4a), `hooks/router-session-context.py`.
**Date:** 2026-08-07. Fixed in PR #25.

## Problem

`SETUP.md` told the manual install path to copy `hooks/router-session-context.py` verbatim into `~/.claude/`. That file carries a `CLAUDE_PLUGIN_OPTION_ENABLE_SESSION_STATUS` gate. The variable is set only inside the plugin runtime, so on every manual install the hook exited 0 with empty stdout. All three check-4a probes failed, and the router status line never appeared in any session. Nothing reported an error.

## Root cause

The gate is deliberate: it keeps the *plugin* distribution dormant until a user opts in. A manual install is wired through `settings.json` and is always-on, governed only by `.router-off`. The install instructions treated the two distributions as one and carried a plugin-only behaviour into the manual path.

## Fix

Phase 3 now copies the hook through a `sed` that deletes the gate block, and check 4a carries a diagnostic note for an empty hook output. The hook itself is unchanged.

## Prevention

- **Before "fixing" a difference between two copies, check whether it is an intentional divergence.** The gate is a deliberate difference between the plugin hook and the manually installed copy. Both the reviewer and the author first proposed deleting the gate from the hook, which would have broken the plugin's opt-in. The fix belonged in the install step that crossed the boundary.
- **A hook that can exit 0 with no output needs an install-time check that expects output**, or a mute install looks the same as a quiet one.
