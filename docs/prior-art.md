# Prior art — and where route-sheet sits

The multi-model space is crowded. Almost all of it routes **per-request, at runtime, invisibly**. route-sheet routes **per-unit, at plan time, as a reviewable artifact**. This page maps the neighbors so you can decide which layer you actually need — they compose more than they compete.

## Runtime model routers (proxy layer)

| Project | What it does | Difference from route-sheet |
|---|---|---|
| [claude-code-router](https://github.com/musistudio/claude-code-router) (~36K★) | Proxy between Claude Code and any provider; picks the model per request type (background / think / long-context), custom router scripts | Swaps *which model answers the next request*. No plan awareness, no security policy, no record of what routed where or why. |
| [Workweave router](https://news.ycombinator.com/item?id=48688700) | "Smart model routing directly in Claude, Codex and Cursor" — per-inference cost/quality routing | Same layer: per-inference, automatic, invisible. |
| [RouteLLM](https://github.com/lm-sys/routellm) / [Not Diamond](https://www.notdiamond.ai/) / [LiteLLM router](https://docs.litellm.ai/docs/routing) | Classifier- or gateway-based strong/weak model routing per query | API-level cost optimization; nothing task- or plan-shaped. |
| Azure OpenAI **Model Router** | A first-party product feature routing across deployed models | Also why nothing should be named "model router." |

## Cross-agent delegation (Claude Code ↔ Codex)

| Project | What it does | Difference |
|---|---|---|
| [claude-delegator](https://github.com/jarrodwatts/claude-delegator) | Codex/Gemini as expert subagents of Claude Code (architect, security, review personas) | Role-based, runtime: *who to ask* by specialty. No policy file, no data-governance constraints, no outcome feedback, no verification discipline imposed on the delegate's output. |
| [codex-delegator](https://github.com/eddiearc/codex-delegator), "Ask Codex"-style skills | Auto-delegate logic-intensive tasks to Codex CLI mid-session | Heuristic, per-moment. Delegation happens when the agent feels like it, not when a reviewed manifest says so. |
| OpenAI's official Codex plugin for Claude Code (July 2026) | First-party review + task delegation from inside Claude Code | Confirms the lane is mainstream; still runtime and per-task. route-sheet's codex-dispatch could use it as transport — the manifest, constraint layer, and re-check are the parts it doesn't have. |
| [cli-agent-orchestrator (CAO)](https://github.com/awslabs/cli-agent-orchestrator) | Supervisor/worker orchestration across Claude Code, Codex, Gemini, Copilot | Runtime delegation topology. Notably, [issue #312](https://github.com/awslabs/cli-agent-orchestrator/issues/312) requests *deterministic, pre-planned* orchestration — plan-time assignment as a felt gap. |

## Enterprise AI gateways

OpenRouter's governance layer, Databricks Unity AI Gateway, and NVIDIA's agent runtimes do policy-driven routing with PII guardrails — **at the organizational API layer**. If your company runs one, it enforces org policy on every API call. It doesn't know your plan exists, can't reason about "this unit is PII-bound but that one isn't," and doesn't cover the personal stack where a solo builder actually works. route-sheet is that governance idea, scaled down to one person's toolchain and moved to where the task context lives.

## Plan-time vs runtime, concretely

| | Runtime routers | route-sheet |
|---|---|---|
| Decision moment | Per request, mid-execution | Per unit, at plan approval |
| Decision visibility | Invisible (log at best) | Reviewed artifact, approved with the plan |
| Decision inputs | Prompt features, token counts, cost dials | Unit shape, spec frozenness, data sensitivity, credential environment |
| Security posture | None / provider ToS | Constraint layer: PII rule, credential scrub, deny-list, cloud-exec approval ([security-model.md](security-model.md)) |
| Verification | Trusts the model's output | Orchestrator re-check per unit; PASS = survived it |
| Learning | Opaque or vendor-side | Human-gated ledger → policy cells ([outcome-ledger.md](outcome-ledger.md)) |
| Audit trail | Reconstructed from logs | The manifest + execution log *are* the trail |

**"Why not just use claude-code-router?"** Use it — if your question is "can a cheaper model serve this request?" It's excellent at that, and it composes with route-sheet (a proxy can sit under any executor). route-sheet answers three questions the proxy layer structurally cannot: *should this work leave my machine at all* (constraint layer), *which parts of this plan are delegable and which aren't* (per-unit shape routing), and *did the delegation actually hold up* (re-check + ledger). Cost routing and governance routing are different problems; the crowded lane is the first one.
