# Local Models — Inventory & Protocol

**Cross-tier routing** — *which task shape goes to a local model vs Codex vs a Claude tier* — lives in `ROUTING_POLICY.md`. This file is the local-model **inventory**: which local model to pick once a task has been routed local, plus capability, parallel-viability, and maintenance facts. The policy's `llocal` rows point here for the model choice.

Example host: Ollama on Apple Silicon (M-series), 128GB unified memory, MLX-optimized backend (v0.24+). Adjust the inventory rows to your hardware — a ~35B model wants ~24GB+ of free unified memory; the ≤7B rows run almost anywhere.

- **Models live at:** `~/.ollama/models` (`OLLAMA_MODELS` unset → default). Blobs in `blobs/`, model list in `manifests/registry.ollama.ai/library/<name>/<tag>`.
- **Binary:** `/usr/local/bin/ollama` · **API:** `http://localhost:11434`
- **Helper:** `~/.claude/bin/llocal` — the only way the agent should invoke these (poll / run / batch). See bottom.
- **Poll (no model load):** `~/.claude/bin/llocal models` → hits `/api/tags`. Cheap; safe to run every time.

---

## Local Model Inventory

Once `ROUTING_POLICY.md` has routed a task to `llocal`, pick the model here. Local models are **weaker than the frontier coordinator** — offload mechanical/bulk/PII work, keep reasoning and the final judgment yourself.

| Model | Type | Best for | Avoid | Parallel (`--workers`) | Size |
|---|---|---|---|---|---|
| `qwen3.5:35b-a3b-coding-nvfp4` | Code/text LLM (35B MoE, ~3B active, MLX) | Code gen/refactor subtasks, batch text classification/extraction/summarization, JSON-schema extraction, autonomous loops | Correctness-critical SQL against prod, architecture decisions, anything shipped unverified. **Reasoning model — never cap with `--num-predict`** (any cap truncates before the answer → empty `out`). | ❌ **no gain** — 35B saturates the GPU per request (benchmarked 2026-06-25: 3 items, w1 52s vs w4 59s). Use `--workers 1`; run big batches sequential in background. | 21.9 GB |
| `llava:13b` | Vision + language (VLM) | Batch screenshot/image OCR & description, visual triage before the coordinator decides | Accuracy-critical vision (frontier models are natively multimodal and better); use only for batch-volume or strict local-only privacy | ❓ untested; likely seq (13B) — benchmark before relying on `--workers` | 8.0 GB |
| `llava:latest` | Vision + language (7B) | Lighter/faster image pass than llava:13b | Same as above; lower quality than :13b | ❓ untested (~7B) — may batch; benchmark before relying on `--workers` | 4.7 GB |

*Parallel legend:* ✅ concurrency helps (set `--workers N` = server `OLLAMA_NUM_PARALLEL=N`) · ❌ no gain, run sequential · ❓ unknown — benchmark once, then record the result here.

*Last reconciled with `llocal models`: 2026-06-25.*

---

## Candidate Models — NOT installed, available via `ollama pull`

Curated shortlist of generally-available Ollama models worth pulling **only if a task fits and no installed model above covers it**. All sized to run on 128GB unified memory (≤~70B dense, or MoE; 405B/671B excluded). **If a task matches a row here and the model isn't installed, PROMPT the user to `ollama pull <name>` — don't silently degrade or burn coordinator tokens on bulk work a local model should do.** Sizes/tags are approximate — confirm at pull time on ollama.com/library.

| Model (`ollama pull`) | Type | Fills which gap / best for | Approx size (q4) |
|---|---|---|---|
| `llama3.1:70b` | General LLM | **Gap: no general-reasoning local model installed** (only code + vision). Tool-use, higher-quality local chat/summarization than the coding qwen. | ~40 GB |
| `qwen3:32b` (or larger MoE) | General LLM (newer gen) | Newer general reasoning; MoE variants efficient. Alt to llama3.1:70b. | ~20 GB+ |
| `deepseek-r1:70b` | Reasoning | Heavy local chain-of-thought on **private data kept off-cloud**. | ~40 GB |
| `qwen2.5-coder:32b` | Code | Stronger/cleaner code-gen than the installed qwen3.5 for larger refactors. | ~20 GB |
| `llama3.2-vision:90b` / `qwen3-vl` | Vision (strong) | Accuracy-critical batch vision beyond llava's quality ceiling. | ~55 GB / varies |
| `nomic-embed-text` | Embeddings | **Gap: no embeddings model installed** — local semantic search / clustering / dedup / RAG over data that must stay local (e.g. customer records). | <1 GB |
| `mxbai-embed-large` | Embeddings | SOTA small embeddings; alt to nomic. | ~0.7 GB |
| `phi4-mini` (3.8B) / `smollm2` | Small-fast | High-volume trivial classification/extraction where even the coding qwen is overkill; fastest fan-out — small enough that `--workers N` + `OLLAMA_NUM_PARALLEL=N` gives **real** concurrency (the parallel-batch lever the big model lacks). | <3 GB |

*Last refreshed from ollama.com/library: 2026-06-25.*

### Refresh protocol (keep this catalog current)
- **Staleness-triggered (primary mechanism):** whenever you consult this catalog, check the "Last refreshed" date. If >30 days old, refresh it — fetch `https://ollama.com/library?sort=popular`, reconcile rows (add notable new models, drop deprecated, fix sizes/tags), update the date. If you can't fetch, tell the user it's stale.
- **On pull:** when the user installs a candidate, move that row up into the installed Routing Table (run `llocal models` to confirm) and update both "Last" dates.
- Keep this curated to high-value gap-fillers for your actual work — the public library has hundreds of models; this is not an exhaustive mirror.

---

## Maintenance Protocol (the agent follows this)

**Every time you reach for a local model:**

1. **Poll:** run `~/.claude/bin/llocal models`.
2. **Reconcile:** compare the output against the table above. If any installed model is **not** in the table, probe it before routing — check `family`/`parameter_size` from the poll, and if unsure run a one-line capability probe (`llocal run <model> "In one line, what kind of model are you and what are you best at?"`) — then **add a row** (Best for / Avoid / Size) and update the "Last reconciled" date.
3. **Route:** state which model you picked and why.
4. **Verify:** read back only the result and sanity-check it before using. Don't pass local-model output downstream unverified.
5. **Record what you learned (so it's not re-derived):** if you benchmarked or determined a model's parallel viability (or any other durable trait — a `--num-predict` quirk, a reasoning-vs-instruct behavior, a timeout pattern), write it into that model's row (the **Parallel** column or **Avoid** cell). A `❓` you resolved should never stay `❓`. The table is the inventory — next session reads the cell instead of re-benchmarking.

Install primarily via Ollama (`ollama pull <name>` / `ollama rm <name>`); browse [ollama.com/library](https://ollama.com/library). This table is the routing source of truth — keep it current.

---

## When to offload (vs. just doing it as the coordinator)

Offload only when local **wins** on something the coordinator can't give you:
- **Batch / fan-out** — same cheap op over many items; keeps the coordinator's context clean and costs no tokens.
- **Privacy** — PII that shouldn't hit the cloud (e.g. inferred customer demographics, raw transaction rows).
- **Tight autonomous loops** — many trivial calls where frontier tokens would be wasted.

Do **not** offload reasoning-heavy or correctness-critical work — that stays on the coordinator.

---

## Parallelism viability (decide BEFORE using `--workers >1`)

Concurrency only buys throughput when the model is small enough that several requests batch into one GPU forward pass. On a single-GPU Metal box a **large model already saturates compute per request**, so concurrent requests just time-slice the same hardware — no speedup, sometimes slightly worse from KV-cache/scheduling overhead. Benchmarked 2026-06-25 (3 items, qwen3.5 35B MoE): `--workers 1` = 52s vs `--workers 4` + `NUM_PARALLEL=4` = 59s.

**Read the Routing Table's Parallel column first** — viability is recorded per model there. Only when it's `❓` do you benchmark (a few items, `--workers 1` vs `--workers N` wall-time), and then **write the result back into the cell** (Maintenance Protocol step 5) so it's a lookup next time, not a re-run.

Decide by model size before parallelizing a batch:

- **Big model (≳13B dense, or the 35B MoE):** `--workers 1`. Don't bother with `NUM_PARALLEL`. For large batches, run sequential in the **background** and let it finish; don't block on it.
- **Small model (≤~7B — `phi4-mini`, `smollm2`, `llava:latest`):** parallelism is real here. Set `--workers N` **and** match `OLLAMA_NUM_PARALLEL=N` on the server (below). This is the lever for fast high-volume fan-out — route bulk classification/extraction to a small model rather than parallelizing the big one.
- Either way: **keep a deterministic ground-truth path and verify every item** — local runners drop/timeout individual requests (3/20 timed out in the 2026-06-25 batch); a missing/garbled completion must not become a missing result.

**Setting `OLLAMA_NUM_PARALLEL` (server-side, must match `--workers`):** when Ollama runs as the macOS app, `serve` inherits env from the GUI session via `launchctl`:
```bash
launchctl setenv OLLAMA_NUM_PARALLEL 4          # session-scoped (gone on reboot)
osascript -e 'tell application "Ollama" to quit'; pkill -f Ollama.app; sleep 2; open -a Ollama
# verify the NEW serve process actually has it (not just launchctl):
ps eww -p "$(pgrep -f 'Ollama.app.*ollama serve' | head -1)" | tr ' ' '\n' | grep OLLAMA_NUM_PARALLEL
```
The AppleScript `quit` alone often doesn't stop `serve` (same PID persists, env not inherited) — confirm the PID changed and the var is in the process env. For durability across reboots, a LaunchAgent running the `setenv` at login.

---

## Helper usage (`llocal`)

```bash
llocal models [--names]                          # poll installed models (no load)

llocal run MODEL "prompt"                         # single completion (arg or stdin)
echo "prompt" | llocal run MODEL
llocal run MODEL "prompt" --system "You are..." --temp 0.2 --num-predict 256
llocal run MODEL "Extract fields" --json '{"type":"object","properties":{"x":{"type":"string"}}}'

llocal batch MODEL items.jsonl                    # one completion per line → JSONL out
#   each line: a bare prompt string, OR {"id": "...", "prompt": "..."}
#   output:    {"id": ..., "out": ...}  or  {"id": ..., "error": ...}  (order preserved)
llocal batch MODEL items.jsonl --workers 4        # concurrent — only worth it for SMALL models; see Parallelism viability above
```

Env: `OLLAMA_HOST` overrides the default endpoint. Stdlib-only Python 3, no deps.
