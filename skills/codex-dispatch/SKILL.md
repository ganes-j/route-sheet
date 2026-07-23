---
name: codex-dispatch
description: Dispatch a spec'd implementation unit to OpenAI Codex (codex exec) with pre-flight safety guards and a mandatory orchestrator re-check. Use when a routing manifest assigns a unit to codex-implementer, or when offloading a frozen-spec implementation, mechanical refactor, bugfix-with-known-repro, or CI/dep/test-bulk unit to Codex. This is Lane B (per-unit) of the model router; the constraint layer lives in ~/.claude/ROUTING_POLICY.md.
---

# Codex Dispatch (Lane B)

Hand one implementation unit to Codex, then verify its output yourself. Codex output is MORE untrusted than a Claude subagent (different model, own sandbox, reasoning hidden) — the re-check is not optional.

**Kill switch:** if `~/.claude/.router-off` exists, do not dispatch — work the unit inline. (The SessionStart hook also injects a disable directive; check the file here regardless.)

Model + reasoning effort inherit from `~/.codex/config.toml` (e.g. `gpt-5.6-sol`, effort `medium`). Do NOT pass `-m` or `-c model_reasoning_effort=…` — config.toml is the single source of truth.

## 1. Pre-dispatch checks (ordered — stop at the first failure)

1. **Kill switch** — `[ -f ~/.claude/.router-off ]` → abort, work inline.
2. **Prod-credential scan** of the dispatch dir, per the constraint layer in `ROUTING_POLICY.md`. Block only on a *live prod credential*, not on `.env` presence:
   ```bash
   # Block if any .env/config in the dispatch dir holds a non-localhost connection-string host.
   scan_dir="$1"
   # Enumerate with find, not `grep -r --include`: BSD grep (macOS) does NOT match a
   # dotfile named `.env` via --include, so grep -r silently misses the real credential
   # and only catches tracked `.env.example` placeholders. find matches `.env` on BSD+GNU.
   # Exclude template files — their placeholder API URLs are not live credentials.
   hits=$(find "$scan_dir" -type f \( -name '.env' -o -name '*.env' -o -name '.env.*' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' \) \
     ! -name '*.example' ! -name '*.sample' ! -name '*.template' \
     -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null \
     | while IFS= read -r f; do grep -hoE '[a-z]+://[^ "'"'"']+' "$f" 2>/dev/null; done \
     | sed -E 's#^[a-z]+://##; s#^[^@]*@##; s#[:/?].*##' \
     | grep -vE '^(localhost|127\.0\.0\.1|::1|0\.0\.0\.0|[^.]+\.local)$' | sort -u)
   if [ -n "$hits" ]; then echo "BLOCK: non-localhost host(s) in dispatch dir: $hits"; fi
   ```
   Dev keys / localhost / SaaS dev keys pass (`dispatch_dir="$repo"`, worktree-free). On a hit, resolve `dispatch_dir` per the constraint layer:
   - **Deny-listed dir** (e.g. `~/work/payments-app/.env` on your policy's deny-list) → **hard-skip, no worktree attempt**: reassign to a non-Codex executor. "Known-dangerous" outranks a clean scan (a worktree could omit a gitignored deny-listed file and read clean).
   - **Host-detection hit, non-deny-listed, authoring unit** → **scrub into a fresh worktree instead of skipping.** A fresh `git worktree` checks out tracked files only, so a gitignored `.env` is not carried in. Create it, then re-run the SAME scan against the worktree:
     ```bash
     git -C "$repo" check-ignore -q .worktrees/ || echo "WARN: .worktrees/ not gitignored — do not scrub here"
     wt="$repo/.worktrees/codex-$unit"
     git -C "$repo" worktree add -q "$wt" HEAD
     rescan=$(find "$wt" -type f \( -name '.env' -o -name '*.env' -o -name '.env.*' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' \) \
       ! -name '*.example' ! -name '*.sample' ! -name '*.template' \
       -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null \
       | while IFS= read -r f; do grep -hoE '[a-z]+://[^ "'"'"']+' "$f" 2>/dev/null; done \
       | sed -E 's#^[a-z]+://##; s#^[^@]*@##; s#[:/?].*##' \
       | grep -vE '^(localhost|127\.0\.0\.1|::1|0\.0\.0\.0|[^.]+\.local)$' | sort -u)
     ```
     `rescan` empty → `dispatch_dir="$wt"`, dispatch there (§2). `rescan` non-empty (a tracked / non-gitignored prod credential the worktree can't drop) → `git -C "$repo" worktree remove "$wt"` and **hard-skip** to a non-Codex executor.
3. **PII constraint** — if the unit is PII-bound, Codex is never allowed (route llocal/coordinator). PII is a property of the task, decided at routing time.
4. **`command -v codex`** — absent → fall back to coordinator, note it.

## 2. Dispatch

Build an XML-tagged prompt from the unit's fields and pipe it via stdin. Verified invocation (Codex 0.143.0 — `--ask-for-approval` is NOT an `exec` flag; exec is non-interactive/`approval: never` by default):

Dispatch into `dispatch_dir` (the worktree when §1.2 scrubbed, else `$repo`):

```bash
scratch=$(mktemp -d -t codex-dispatch-XXXXXX)
codex exec -s workspace-write -C "$dispatch_dir" \
  -o "$scratch/last-message.txt" \
  - < "$scratch/prompt.md" > "$scratch/run.log" 2>&1 &
codex_pid=$!
```

Prompt (`prompt.md`) sections, filled from the unit: `<task>` (Goal), `<files>` (Files list), `<patterns>` (Patterns to follow), `<approach>`, `<constraints>` (Modify only the listed files; do NOT git add/commit/push; keep the change scoped), `<verify>` (the unit's load-bearing check command), `<output>` (report what you changed + verification result).

- **Session ID** (for never-`resume --last`-in-parallel): parse the banner — `grep '^session id:' "$scratch/run.log"`. Use the explicit ID on any `codex exec resume <id>`.
- **Never** `--dangerously-bypass-approvals-and-sandbox` on work repos.
- **`codex cloud exec`** (full-repo upload to OpenAI — distinct trust boundary): only with explicit per-unit user approval via a blocking question. Never auto.
- **Parallel units:** git-worktree per unit + separate `-o` files; never share a working tree or reuse `resume --last`.

## 3. Termination

Terminate on the background process exiting (`wait $codex_pid`). Hang breaker: a generous per-unit wall-clock ceiling (~30 min; small frozen-spec units observed at ~20s). On ceiling breach, kill the process and treat as a failed run (step 4 revert).

## 4. Orchestrator re-check (mandatory — the trust boundary)

Never trust Codex's own "done." After the run:

1. **Read the actual diff:** `git -C "$dispatch_dir" --no-pager diff` (the worktree when §1.2 scrubbed).
2. **Scope check (prompt-injection guard):** confirm only the unit's declared files changed. Any out-of-scope file touch → treat as failure, revert.
3. **Integrate + re-run the load-bearing check yourself against the real env** — the exact command from the manifest entry / `<verify>` (test, build, data-shape check). Do not accept Codex's report; run it. **When `dispatch_dir` was a scrub worktree, Codex authored blind to the credential — the coordinator is the only one who can verify against the resource:** integrate the worktree diff into the working tree (merge/apply into `$repo`), run the check there where the real `.env` lives, then `git -C "$repo" worktree remove "$wt"`. When `dispatch_dir` was `$repo` directly, run the check in place.
4. **On pass** → append an outcome line to the plan's routing manifest execution log, in the **canonical grammar** (`ROUTING_POLICY.md` §6 — the single source of truth; fill real values, not the literals):
   `U<N> · codex-implementer · PASS · re-check <cmd> <green|red> · <N> fix rounds · <session-id> · <YYYY-MM-DD>`
   The unit is not done until this line exists. When you captured a replay bundle for the unit (per §6 **Replay-bundle capture**), append the optional trailing ` · base:<sha>` token with the pre-unit base commit — this is what makes the unit replayable in a later bake-off. (Codex units are impl-from-frozen-spec, which the shipped single-shot runner does not replay yet — so **skip capture for them** until the U9 harness track enables impl-unit replay; emit the outcome line without a `base:` token.)
5. **On fail** (re-check red, empty diff, out-of-scope touch, or hang) → revert (`git -C "$dispatch_dir" checkout -- .`; if a scrub worktree, `git -C "$repo" worktree remove --force "$wt"` and drop any integration), increment the consecutive-failure counter, and the **coordinator implements the unit directly**. Emit a `FALLBACK` outcome line (§6 grammar) in the manifest execution log AND append a drift line to `ROUTING_POLICY.md` §5 with the rationale (the two are paired).
6. **Assignment scope (gate iterations).** A unit's assignment covers its own fix/iteration rounds for **in-scope corrections only** (`ROUTING_POLICY.md` §7). Re-dispatching after a correction — feedback that changes how the unit meets its *existing* goal/files/verify — is still this unit's dispatch, absorbed as additional fix rounds on its outcome line. A gate-surfaced **scope addition** is NOT covered: it takes the §7 path (explicit acceptance + a route-plan mini-pass row or a `## Follow-ons` entry), never extra fix rounds on this unit. Never dispatch remediation from gate feedback without the §7 propose-confirm-dispatch beat.

## 5. Circuit breaker

Track consecutive Codex failures across the run. **3 consecutive failures → disable Codex for the rest of this run**, complete remaining units on the coordinator, and note it. One failure is often a bad spec, not a bad executor — do not flip the policy cell on a single failure (that's the flywheel's job, per `ROUTING_POLICY.md` §3).

## 6. Lane selection (A vs B)

- **All substantive units in the plan route to Codex → Lane A** (whole-plan): invoke `ce-work-beta` with a typed `delegate:codex` argument. First seed the repo's `.compound-engineering/config.local.yaml` with `work_delegate_sandbox: full-auto` (sandbox key only — NEVER persist `work_delegate: codex`, which would delegate while the kill switch is off). Run the prod-credential scan (§1.2) before invoking — ce-work-beta won't. ce-work-beta skips independent verification, so still apply the §4 re-check per batch.
- **Mixed plan (some units Codex, some not) → Lane B** — this skill, per unit. Per-unit routing inside ce-work-beta is not supported (its `delegation_active` is a per-run boolean).
