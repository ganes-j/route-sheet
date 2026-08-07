# CLAUDE.md router section (template)

Insert everything between the START/END markers into your always-loaded agent instructions file (`~/.claude/CLAUDE.md` for Claude Code). The markers make the block surgically removable — revert by deleting the marked block. SETUP.md inserts and verifies this for you.

---

```markdown
<!-- MODEL ROUTER START (revert: delete this whole marked block) -->
# Model Router

Route each unit of multi-unit work to the executor best suited for it rather than doing everything
in the main loop. Read `~/.claude/ROUTING_POLICY.md` for the policy, the constraint layer, and the
task-shape table; it points on to `~/.claude/LOCAL_MODELS.md` for the local-model lane.

- **At plan time (`/ce-plan`, or your planner's equivalent):** run the **route-plan** skill to write
  a sidecar `<plan-basename>-routing.md` beside the plan file, assigning each U-ID an executor. A
  plan without its manifest is not finished.
- **At execution (`/ce-work`, or your execute step):** read that sidecar manifest and dispatch each
  unit to its executor. `codex-implementer` units go through **codex-dispatch**, never a raw
  `codex exec`. Dispatch is default-binding: running a manifest-assigned unit inline needs a
  rationale logged to the manifest execution log and `ROUTING_POLICY.md` §5. A unit with no manifest
  row goes to the §2 fallback ladder; review-gate feedback goes to §7.
- **A unit is not done until its outcome line exists** in the manifest execution log (ad-hoc work:
  `~/.claude/router-adhoc-outcomes.md`), written in the `ROUTING_POLICY.md` §6 grammar. That log is
  the flywheel's primary routed-outcome input.
- **At `/ce-compound`, or your retrospective step:** run the **router-flywheel** skill. It stays
  dry-run until the R0 gate passes.
- **PII-bound work never goes to Codex**, and the coordinator (you) keeps architecture, destructive
  ops, GitHub mutations, and the verification gate. Full constraint layer: `ROUTING_POLICY.md` §1.

Kill switch: if `~/.claude/.router-off` exists the router is OFF, so work inline with no routing or
delegation. `touch` it to disable, `rm` to re-enable.
<!-- MODEL ROUTER END -->
```
