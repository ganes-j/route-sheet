"""Tests for the idle-gated bake-off cron wrapper (U2)."""

import importlib.util
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


CRON_PATH = Path(__file__).parents[1] / "bin" / "bakeoff-cron"
# Extensionless file → load via SourceFileLoader (spec_from_file_location can't
# infer a loader without a .py suffix).
_loader = SourceFileLoader("bakeoff_cron", str(CRON_PATH))
_spec = importlib.util.spec_from_loader("bakeoff_cron", _loader)
cron = importlib.util.module_from_spec(_spec)
_loader.exec_module(cron)


class FakeSweep:
    def __init__(self):
        self.called = 0

    def __call__(self):
        self.called += 1
        class R:
            returncode = 0
        return R()


class BakeoffCronTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "router-bakeoff.log"
        self.off = Path(self.tmp.name) / ".router-off"  # not created unless a test does

    def tearDown(self):
        self.tmp.cleanup()

    def test_kill_switch_skips_sweep(self):
        self.off.write_text("", encoding="utf-8")
        sweep = FakeSweep()
        outcome = cron.run_cron(
            router_off_path=str(self.off), log_path=str(self.log),
            session_active_fn=lambda: False, sweep_fn=sweep,
        )
        self.assertEqual(outcome, "skipped-killswitch")
        self.assertEqual(sweep.called, 0)
        self.assertIn("kill switch", self.log.read_text(encoding="utf-8"))

    def test_active_session_defers_sweep(self):
        sweep = FakeSweep()
        outcome = cron.run_cron(
            router_off_path=str(self.off), log_path=str(self.log),
            session_active_fn=lambda: True, sweep_fn=sweep,
        )
        self.assertEqual(outcome, "deferred-session")
        self.assertEqual(sweep.called, 0)
        self.assertIn("session is active", self.log.read_text(encoding="utf-8"))

    def test_clear_path_runs_sweep(self):
        sweep = FakeSweep()
        outcome = cron.run_cron(
            router_off_path=str(self.off), log_path=str(self.log),
            session_active_fn=lambda: False, sweep_fn=sweep,
        )
        self.assertEqual(outcome, "swept")
        self.assertEqual(sweep.called, 1)
        self.assertIn("swept: bakeoff --sweep exit=0", self.log.read_text(encoding="utf-8"))

    def test_log_is_appended_not_truncated(self):
        self.log.write_text("2026-01-01T00:00:00 prior line\n", encoding="utf-8")
        cron.run_cron(
            router_off_path=str(self.off), log_path=str(self.log),
            session_active_fn=lambda: False, sweep_fn=FakeSweep(),
        )
        contents = self.log.read_text(encoding="utf-8")
        self.assertIn("prior line", contents)  # preserved
        self.assertIn("swept:", contents)       # appended

    def test_own_pid_not_counted_as_active_session(self):
        # A pgrep that returns only our own PID must not read as an active session.
        import os
        outcome = cron.run_cron(
            router_off_path=str(self.off), log_path=str(self.log),
            session_active_fn=lambda: cron.claude_session_active(
                pgrep_fn=lambda: [str(os.getpid())]
            ),
            sweep_fn=FakeSweep(),
        )
        self.assertEqual(outcome, "swept")  # own pid filtered out → not active → swept


if __name__ == "__main__":
    unittest.main()
