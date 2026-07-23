"""Tests for the SessionEnd bake-off sweep hook (U3)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


HOOK_PATH = Path(__file__).parents[1] / "hooks" / "bakeoff-sweep.py"
_spec = importlib.util.spec_from_file_location("bakeoff_sweep", HOOK_PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


class FakePopen:
    calls = []

    def __init__(self, argv, **kwargs):
        FakePopen.calls.append((argv, kwargs))


class SweepHookTests(unittest.TestCase):
    def setUp(self):
        FakePopen.calls = []
        self.tmp = tempfile.TemporaryDirectory()
        self.bakeoff = Path(self.tmp.name) / "bakeoff"
        self.bakeoff.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_kill_switch_present_launches_nothing(self):
        off = Path(self.tmp.name) / ".router-off"
        off.write_text("", encoding="utf-8")

        fired = hook.sweep_fire(
            self.bakeoff,
            ["~/.claude/plans/*-routing.md"],
            router_off_path=str(off),
            popen=FakePopen,
        )

        self.assertEqual(fired, [])
        self.assertEqual(FakePopen.calls, [])

    def test_kill_switch_absent_fires_detached_sweep(self):
        off = Path(self.tmp.name) / ".router-off"  # not created
        plans = Path(self.tmp.name) / "plans"
        plans.mkdir()
        (plans / "demo-plan-routing.md").write_text("## Assignments\n", encoding="utf-8")
        glob = str(plans / "*-routing.md")

        fired = hook.sweep_fire(
            self.bakeoff,
            [glob],
            router_off_path=str(off),
            popen=FakePopen,
        )

        self.assertEqual(fired, [glob])
        self.assertEqual(len(FakePopen.calls), 1)
        argv, kwargs = FakePopen.calls[0]
        self.assertIn("--sweep", argv)
        self.assertIn(str(self.bakeoff), argv)
        # non-blocking + detached contract: new session, no wait primitive used
        self.assertTrue(kwargs.get("start_new_session"))

    def test_glob_with_no_matching_manifest_fires_nothing(self):
        off = Path(self.tmp.name) / ".router-off"  # not created
        fired = hook.sweep_fire(
            self.bakeoff,
            [str(Path(self.tmp.name) / "plans" / "*-routing.md")],  # dir does not exist
            router_off_path=str(off),
            popen=FakePopen,
        )
        self.assertEqual(fired, [])
        self.assertEqual(FakePopen.calls, [])

    def test_missing_runner_is_a_noop(self):
        off = Path(self.tmp.name) / ".router-off"
        fired = hook.sweep_fire(
            Path(self.tmp.name) / "does-not-exist",
            ["docs/plans/*-routing.md"],
            router_off_path=str(off),
            popen=FakePopen,
        )
        self.assertEqual(fired, [])
        self.assertEqual(FakePopen.calls, [])

    def test_main_never_raises_and_returns_zero(self):
        # main() must swallow any error — a measurement sweep never breaks the session.
        self.assertEqual(hook.main(), 0)


if __name__ == "__main__":
    unittest.main()
