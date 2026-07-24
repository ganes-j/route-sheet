# SETUP.md — agent-executable install

This runbook is written for an agent (Claude Code or equivalent) executing on a user's behalf. Humans can follow it too — every step is a plain shell command with its expected output.

**Agent contract — read first:**
- Execute phases in order. Never skip a consent gate. All writes are idempotent: check before writing, append rather than overwrite, and never clobber an existing file silently — on any conflict, show the diff and ask.
- Every verify step states its expected output. Paste the *actual* output in your report. If a verify fails, stop that tier and report it — do not claim it.
- Finish with the **honest tier report** (Phase 5). "Tier 1 achieved, Tier 2 unavailable: codex not found" is a successful install. A silent partial success is a failed one.
- `$RS` below means the absolute path of this repo's checkout.

---

## Phase 1 — Preflight (read-only, run everything)

Probe capabilities; decide the target tier. Nothing here writes.

| # | Probe | Command | Interpreting the output |
|---|---|---|---|
| 1 | Claude Code home | `test -d ~/.claude && echo ok` | `ok` → proceed. Anything else → you are not on a Claude Code host; Tier 0 only. |
| 2 | U-ID plan workflow (optional) | Check your available skills for `ce-plan` (compound-engineering plugin). | Present → routing consumes its U-ID'd plans directly. Absent → still fine: route-plan mints U-IDs from an ID-less TODO/tasklist/pasted plan, so Tier 1 is fully usable; note in the report that minting is the input path. |
| 3 | Verification discipline | Check your available skills for `verification-before-completion` (superpowers plugin). | Absent is non-blocking — note in the report that the re-check gate has no enforcement backstop. |
| 4 | Python | `python3 --version` | 3.9+ → ok. |
| 5 | git worktrees | `git --version` | Any modern git → ok (Tier 2 scrub path). |
| 6 | Codex CLI | `command -v codex && codex --version` | Present → Tier 2 possible. Absent → Tier 2 unavailable. |
| 7 | Codex config pin | `test -f ~/.codex/config.toml && grep -c '^model' ~/.codex/config.toml` | `1`+ → pinned. Present-but-unpinned or absent → Tier 2 degraded; instruct the user to pin a model (never write this file yourself — it may hold auth). |
| 8 | Ollama server | `curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null && echo up` | `up` → Tier 3 possible. Anything else → Tier 3 unavailable. |
| 9 | Local models | `command -v ollama && ollama list` | Note which models exist; [templates/LOCAL_MODELS.md](templates/LOCAL_MODELS.md) rows want a coding model and optionally a vision model. |

**Target tier** = 1 + (Tier 2 if probes 6–7 pass) + (Tier 3 if probe 8 passes). Announce it before Phase 2.

---

## Phase 2 — Consent gate (blocking)

Present the exact write list for the target tier and get a yes before any write.

**Tier 1 writes:**
- Copy → `~/.claude/ROUTING_POLICY.md` (from `templates/ROUTING_POLICY.md`)
- Copy → `~/.claude/ROUTER_STATUS.md` (from `templates/ROUTER_STATUS.md`, with today's date filled in)
- Copy → `~/.claude/skills/route-plan/SKILL.md`, `~/.claude/skills/router-flywheel/SKILL.md`
- Copy → `~/.claude/router-session-context.py` (from `hooks/`)
- Merge → one SessionStart hook entry into `~/.claude/settings.json`
- Insert → the marker-bounded block from `templates/claude-md-router-section.md` into `~/.claude/CLAUDE.md`

**Tier 2 adds:** copy → `~/.claude/skills/codex-dispatch/SKILL.md`. (No writes to `~/.codex/` — ever.)

**Tier 3 adds:** copy → `~/.claude/bin/llocal` (`chmod +x`), copy → `~/.claude/LOCAL_MODELS.md`.

Nothing else is touched. The user can exclude any item; record exclusions for the report.

---

## Phase 3 — Apply (idempotent)

For every **file copy**: if the destination doesn't exist, copy. If it exists and is identical, skip and note "already installed." If it exists and differs, show the diff and ask before replacing. Suggested shape:

```bash
dst=~/.claude/ROUTING_POLICY.md; src="$RS/templates/ROUTING_POLICY.md"
if [ ! -f "$dst" ]; then cp "$src" "$dst" && echo "installed $dst"
elif diff -q "$src" "$dst" >/dev/null; then echo "already installed (identical)"
else echo "CONFLICT — showing diff, asking user"; diff "$dst" "$src"; fi
```

**CLAUDE.md block** — marker-bounded, insert-once:

```bash
grep -q 'MODEL ROUTER START' ~/.claude/CLAUDE.md 2>/dev/null \
  && echo "block already present — leaving untouched" \
  || { printf '\n'; sed -n '/^<!-- MODEL ROUTER START/,/^<!-- MODEL ROUTER END -->/p' \
       "$RS/templates/claude-md-router-section.md"; } >> ~/.claude/CLAUDE.md
```

(The `sed` extracts only the marked block from the template, skipping the template's own explanatory header. Create `~/.claude/CLAUDE.md` first if it doesn't exist.)

**settings.json hook** — merge, never overwrite. Add this entry to the `hooks.SessionStart` array (matcher `startup|resume|clear|compact`) only if no existing entry mentions `router-session-context.py`:

```json
{ "type": "command", "command": "python3 ~/.claude/router-session-context.py 2>/dev/null || true", "async": false }
```

Use a JSON-aware merge (python3 + `json` module), preserve every existing hook, and write back with the original structure. If `settings.json` doesn't exist, create it with only this hook. Show the user the resulting `SessionStart` array.

**ROUTER_STATUS.md** — replace both `YYYY-MM-DD` placeholders with today's date and note the installed tier in the log line.

---

## Phase 4 — Verify (run every check for the installed tier; paste outputs)

**4a. Hook + kill switch (Tier 1):**
```bash
python3 ~/.claude/router-session-context.py            # expect: {"hookSpecificOutput": ... "MODEL ROUTER: ACTIVE ..."}
touch ~/.claude/.router-off
python3 ~/.claude/router-session-context.py            # expect: ... "MODEL ROUTER: DISABLED ..."
rm ~/.claude/.router-off
python3 ~/.claude/router-session-context.py            # expect: ACTIVE again
```
All three must exit 0 with the expected strings. **Do not leave `.router-off` behind.**

**4b. Files landed (Tier 1):**
```bash
ls ~/.claude/ROUTING_POLICY.md ~/.claude/ROUTER_STATUS.md \
   ~/.claude/skills/route-plan/SKILL.md ~/.claude/skills/router-flywheel/SKILL.md
grep -c 'MODEL ROUTER START' ~/.claude/CLAUDE.md        # expect: 1  (exactly — 2+ means a double insert; fix it)
```

**4c. Routing smoke test (Tier 1) — the load-bearing check.** Perform the route-plan procedure (as installed at `~/.claude/skills/route-plan/SKILL.md`) against the bundled fixture plan `fixtures/sample-plan/plan.md`, writing the manifest to a scratch directory — not into this repo. Then compare your manifest's `## Assignments` against `fixtures/sample-plan/expected-routing.md`: **the executor per U-ID must match** (reasons may be worded differently). A mismatch means the policy or skill didn't install correctly — diagnose before reporting.

**4c-bis. Minting smoke test (Tier 1) — verifies the ID-less input path.** Copy `fixtures/todo-plan/todo.md` to a scratch file first (leave the repo fixture ID-less for future runs), then run the route-plan procedure against that scratch copy — it has **no** `### U<N>.` headings. route-plan must mint `[U<N>]` markers (writing them back to the scratch copy on consent) and produce a manifest matching `fixtures/todo-plan/expected-routing.md` on **executor AND discipline label per U-ID**. The three assertions there — minting happened, full/bare labels correct, and no bare unit on a write-worker — must all hold. A bare unit routed to codex-implementer or llocal-batch is a fail.

**4d. Codex lane (Tier 2):** `command -v codex` and re-confirm the config pin (probe 7). Do **not** run a live dispatch as part of setup.

**4e. Local lane (Tier 3):**
```bash
~/.claude/bin/llocal models      # expect: a table of installed models, or a clean error naming the Ollama endpoint
```
If no coding model is installed, recommend one from `~/.claude/LOCAL_MODELS.md` — recommend, don't pull (multi-GB download needs consent).

**4f. New-session check (Tier 1):** the SessionStart hook fires on the *next* session. Tell the user: after restarting the session, the context should contain `MODEL ROUTER: ACTIVE`.

---

## Phase 5 — The honest tier report

End with exactly this shape, filled with real results:

```
route-sheet install report
- Tier achieved: <0|1|2|3>
- Verified: <each 4a–4e check run, with actual output pasted or summarized>
- Unavailable: <tier — concrete reason, e.g. "Tier 2 — codex not found on PATH">
- Excluded by user: <consent-gate exclusions, or none>
- Notes: <plugin gaps from preflight probes 2–3; model recommendations; next-session hook check>
```

Never round a partial install up. The report is the deliverable.

---

## Optional — OpenRouter model intelligence (read-only)

Enhances the model-awareness refresh ([templates/MODEL_REFRESH.md](templates/MODEL_REFRESH.md)) with live OpenRouter data. Read-only and independent of the tiers — skip it and the refresh uses its existing sources.

- **Factual (no setup, no auth):** `bin/openrouter_facts.py` reads OpenRouter's public `/api/v1/models` over HTTPS. Nothing to install or authenticate — it needs only network.
- **Discovery (optional, needs the MCP):** connect the OpenRouter MCP so a refresh can read live rankings for model discovery. Create a free OpenRouter account, then add the remote MCP:
  ```bash
  claude mcp add --transport http openrouter https://mcp.openrouter.ai/mcp
  ```
  First use runs an OAuth flow that mints a **read-only** key (7-day expiry, revocable, separate from your other keys). The refresh calls only read-only tools. If the key expires, factual refresh still works (it uses the auth-free public REST path) and discovery falls back silently.

---

## Optional — automatic bake-off replays (Tier 3 + capture)

Once bake-off bundles are being captured (single-shot units), an idle-gated launchd agent drains them on a schedule so evidence accumulates without you thinking about it. Independent of the tiers — skip it and run `bakeoff --sweep` by hand when you want.

- **Install:** copy `templates/com.route-sheet.bakeoff-sweep.plist` to `~/Library/LaunchAgents/`, replace `__CRON_PATH__` with the absolute path to `bakeoff-cron` and `__LOG_DIR__` with an absolute log dir, then `launchctl load ~/Library/LaunchAgents/com.route-sheet.bakeoff-sweep.plist`. It fires hourly; `bakeoff-cron` skips on `.router-off` and defers while a Claude session is active (no GPU contention).
- **Visibility:** a one-line digest appears at SessionStart (`router-session-context.py`), and every run is logged to `~/.claude/router-bakeoff.log`.
- **Note:** this replaces the earlier `SessionEnd` sweep hook — if you wired one, remove the `bakeoff-sweep.py` `SessionEnd` entry from `settings.json`.
- **Uninstall:** `launchctl unload ~/Library/LaunchAgents/com.route-sheet.bakeoff-sweep.plist`.

---

## Uninstall / disable

- **Soft-disable (reversible, instant):** `touch ~/.claude/.router-off`. Every skill declines; the hook announces DISABLED. Re-enable: `rm ~/.claude/.router-off`.
- **Full removal:** delete the copied files (Phase 2 list), remove the marker-bounded block from `~/.claude/CLAUDE.md` (everything between and including the `MODEL ROUTER START`/`END` comments), and remove the `router-session-context.py` entry from `settings.json`'s SessionStart hooks.
