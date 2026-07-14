# Router Status

The router's small mutable state file. The `router-flywheel` skill greps the `R0 status:` line here to decide dry-run vs live; keep the line's shape exactly.

R0 status: PENDING — 0/3 consecutive real `/ce-plan` runs with unprompted manifests (as of YYYY-MM-DD). Flip to `R0 status: PASSED (<date>)` only after 3 consecutive unprompted manifests on real, *unrelated* plans (a plan about the router itself does not count).

## Log

- YYYY-MM-DD — installed via route-sheet SETUP.md at Tier <n>.
