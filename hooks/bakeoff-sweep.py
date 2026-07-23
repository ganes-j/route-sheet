#!/usr/bin/env python3
"""SessionEnd hook — fire the bake-off replay sweep over pending bundles.

Best-effort and non-blocking: it launches `bakeoff --sweep` in a detached
process and returns immediately, so a replay survives the session ending and
never delays it. Gated by the `~/.claude/.router-off` kill switch, mirroring
`router-session-context.py`. Any failure exits 0 — a measurement sweep must
never surface an error into the session lifecycle.

Layout-agnostic: locates the `bakeoff` runner whether this hook lives in the
plugin (`hooks/` beside `bin/bakeoff`) or the live twin (`~/.claude/` beside
`bakeoff`).
"""

import os
import subprocess
import sys
from pathlib import Path


ROUTER_OFF = "~/.claude/.router-off"

# Manifest globs the sweep scans: the live plans dir always, plus a repo's
# docs/plans when the session ran inside one.
DEFAULT_GLOBS = (
    "~/.claude/plans/*-routing.md",
    "docs/plans/*-routing.md",
)


def _find_bakeoff(here: Path) -> Path | None:
    """Probe the two known layouts for the runner."""
    candidates = (
        here.parent / "bin" / "bakeoff",   # plugin: hooks/ beside bin/
        here.parent / "bakeoff",           # live twin: root sibling
        here.with_name("bakeoff"),
    )
    for c in candidates:
        if c.exists():
            return c
    return None


def sweep_fire(
    bakeoff_path,
    globs,
    *,
    router_off_path=ROUTER_OFF,
    popen=subprocess.Popen,
):
    """Launch a detached sweep per non-empty glob unless the kill switch is set.

    Returns a list of the globs fired (empty when the kill switch is present or
    the runner is missing). Never blocks: uses ``start_new_session`` and does
    not wait on the child.
    """
    if os.path.exists(os.path.expanduser(router_off_path)):
        return []
    if not bakeoff_path or not Path(bakeoff_path).exists():
        return []

    fired = []
    for glob in globs:
        expanded = os.path.expanduser(glob)
        popen(
            [sys.executable, str(bakeoff_path), "--sweep", expanded],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        fired.append(glob)
    return fired


def main():
    try:
        sweep_fire(_find_bakeoff(Path(__file__).resolve()), DEFAULT_GLOBS)
    except Exception:  # noqa: BLE001 - a measurement sweep never breaks the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
