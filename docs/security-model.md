# Security model

This is the part of route-sheet with no public equivalent: a **data-governance constraint layer for cross-vendor delegation**, enforced before any task-shape routing. Runtime routers optimize cost and quality; none of them answer "is this work *allowed* to go to that executor?" This page does.

## Constraint precedence

```
constraints  >  task-shape table  >  preference
```

The constraint layer (`ROUTING_POLICY.md` §1) is checked BEFORE the table. A unit that perfectly matches a Codex-friendly shape but trips a constraint does not go to Codex — no override, no auto-mode exception.

## Rule 1 — PII never routes to a third-party executor

PII-bound work goes to `llocal` (on-device) or the coordinator. Never Codex, local or cloud.

The load-bearing subtlety: **PII is a property of the task, decided at routing time — not of the directory.** A credential scan can't catch "this unit will classify customer records," because the records may arrive at runtime from a database, an API, or a file the scan never saw. So the PII call is made by the router when it reads the unit, not by a detector when it scans a folder. Directory scanning handles credentials (below); task-level judgment handles data.

## Rule 2 — the prod-credential gate (with worktree scrub)

The failure mode: you dispatch a vendor CLI into a repo whose `.env` holds a live production connection string. The sandbox can read the working directory; the credential is now inside another vendor's execution environment.

The gate's default is **allow** — `.env` *presence* alone blocks nothing, because blocking on every dotenv would make the Codex lane useless on real projects. Block only on a *live prod credential*:

```
                         unit routed to codex-implementer
                                      │
                     dispatch dir on the prod DENY-LIST?
                        │yes                        │no
                  HARD-SKIP to a             scan .env/config files for
                  non-Codex executor         connection-string hosts
                  (no worktree attempt)         │
                                    non-localhost host found?
                                   │no                     │yes
                             dispatch directly        AUTHORING unit?
                             (worktree-free)          │yes            │no
                                            scrub: fresh git      hard-skip
                                            worktree (tracked
                                            files only → gitignored
                                            .env not carried in)
                                                  │
                                            re-run the SAME scan
                                            against the worktree
                                            │clean          │still dirty
                                    dispatch into        remove worktree,
                                    the worktree         HARD-SKIP
```

Detection is deliberately simple and greppable: extract hosts from `://` values in `.env`/config files, strip `user:pass@`, block on any host outside {`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `*.local`}. Dev API keys, localhost URLs, and SaaS dev keys pass. (Implementation note that cost a real debugging session: on macOS, BSD grep's `--include='.env'` silently misses dotfiles — enumerate with `find` instead. The shipped scan in [codex-dispatch](../skills/codex-dispatch/SKILL.md) does.)

**Why scrub instead of skip.** Codex units are *authoring-only* — the coordinator owns execution and verification (Rule 4), so Codex never actually needs the credential. A fresh `git worktree` checks out tracked files only; the gitignored `.env` is simply not there. Author in the worktree, then the coordinator integrates the diff back into the real working tree and runs the load-bearing check where the credential lives — the one party that may see the credential is the one that verifies against it. Skipping the repo entirely would mean the capability never runs anywhere credentials exist, which in practice means most of your real work.

**Why the deny-list beats a clean scan.** Deny-listed dirs hard-skip *always*, with no worktree attempt. A worktree omits gitignored files, so it would scan clean even when the parent dir is known-dangerous — "known-dangerous" outranks "scan came back clean." The deny-list encodes what you know; the scanner catches what you forgot.

## Rule 3 — cloud execution is a separate trust boundary

`codex exec` runs locally in a sandbox that sees one directory. `codex cloud exec` **uploads the full repo to the vendor**. Those are different decisions, so the second one is never automated: explicit per-unit, blocking yes/no approval, never selected by a latency or fan-out threshold, never in auto mode.

The same reasoning gates persistence: Lane A whole-plan delegation activates by typed argument only, and its activation key is never written into repo config — persisted config would keep delegating even while the kill switch is on.

## Rule 4 — the never-delegate set

Some work stays on the coordinator regardless of shape match:

- architecture / API design, and spec-writing-as-the-work (judgment is the deliverable)
- tiny edits (<~20 lines) — the dispatch overhead exceeds the work
- anything needing session-scoped tools: MCP servers, browser, password-manager/secrets
- destructive operations and GitHub mutations
- **the verification/review gate itself** — including reviewing Codex-written output; the worker never grades its own homework

## Rule 5 — the orchestrator re-check is the trust boundary

Cross-vendor output is *more* untrusted than a same-model subagent: different model, own sandbox, hidden reasoning. So no worker's "done" is accepted. The coordinator (1) reads the actual diff, (2) runs a scope check — only the unit's declared files may change; an out-of-scope touch is treated as failure and reverted, which doubles as a prompt-injection guard — and (3) re-runs the unit's load-bearing check itself against the real environment. Only then does the outcome line get written. A circuit breaker (3 consecutive worker failures → disable that lane for the rest of the run) bounds the blast radius of a bad day.

## What this model does not cover

Honest edges: it trusts `git check-ignore` and the tracked-file model (a *tracked* credential defeats the scrub — that's the still-dirty hard-skip); the host scan reads `.env`/config shapes, not every conceivable secret format; and it governs *delegation*, not the coordinator's own access — the main agent still holds whatever your session holds. Extend the deny-list and scan patterns as you encounter new shapes.
