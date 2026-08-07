# CLAUDE.md router section (template)

Insert everything between the START/END markers into your always-loaded agent instructions file (`~/.claude/CLAUDE.md` for Claude Code). The markers make the block surgically removable — revert by deleting the marked block. SETUP.md inserts and verifies this for you.

---

```markdown
<!-- MODEL ROUTER START (revert: delete this whole marked block) -->
# Model Router

Route each unit of multi-unit work to the executor best suited for it rather than doing everything
in the main loop. Policy, constraint layer, and the task-shape table: `ROUTING_POLICY.md`.

- **At `/ce-plan`:** run the **route-plan** skill to write `<plan-basename>-routing.md`, assigning
  each U-ID an executor. A plan without its manifest is not finished.
- **At `/ce-work`:** read that manifest and dispatch each unit to its executor. Codex units go
  through **codex-dispatch**, never a raw `codex exec`. Dispatch is default-binding: running a
  manifest-assigned unit inline needs a logged rationale.
- **A unit is not done until its outcome line exists** in the manifest execution log, in the
  `ROUTING_POLICY.md` §6 grammar. That log is the flywheel's only input.
- **PII-bound work never goes to Codex**, and the coordinator keeps architecture, destructive ops,
  GitHub mutations, and the verification gate. Full constraint layer: `ROUTING_POLICY.md` §1.

Kill switch: `~/.claude/.router-off`. SessionStart reports the active state.
<!-- MODEL ROUTER END -->
```
