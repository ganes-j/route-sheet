"""Integration tests for the SessionStart router context hook."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOK_PATH = (
    Path(__file__).resolve().parents[1] / "hooks" / "router-session-context.py"
)


class RouterSessionContextTests(unittest.TestCase):
    def run_hook(self, home):
        env = os.environ.copy()
        env.update(
            {
                "CLAUDE_PLUGIN_OPTION_ENABLE_SESSION_STATUS": "true",
                "HOME": str(home),
                "OLLAMA_HOST": "127.0.0.1:1",
            }
        )
        result = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]

    def write_ledger(self, home, lines):
        claude_dir = Path(home) / ".claude"
        claude_dir.mkdir()
        ledger = claude_dir / "router-field-records.jsonl"
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_missing_ledger_emits_dormant_digest_and_valid_json(self):
        with tempfile.TemporaryDirectory() as tempdir:
            context = self.run_hook(tempdir)

        self.assertIn("BAKE-OFF: idle — no field records yet", context)

    def test_router_off_suppresses_digest_and_emits_disabled_context(self):
        with tempfile.TemporaryDirectory() as tempdir:
            claude_dir = Path(tempdir) / ".claude"
            claude_dir.mkdir()
            (claude_dir / ".router-off").touch()

            context = self.run_hook(tempdir)

        self.assertIn("MODEL ROUTER: DISABLED", context)
        self.assertNotIn("BAKE-OFF:", context)

    def test_state_write_failure_is_swallowed(self):
        with tempfile.TemporaryDirectory() as tempdir:
            state_path = Path(tempdir) / ".claude" / ".bakeoff-digest-state"
            state_path.mkdir(parents=True)

            context = self.run_hook(tempdir)

        self.assertIn("MODEL ROUTER: ACTIVE", context)
        self.assertNotIn("BAKE-OFF:", context)

    def test_ledger_read_failure_preserves_marker(self):
        with tempfile.TemporaryDirectory() as tempdir:
            claude_dir = Path(tempdir) / ".claude"
            ledger_path = claude_dir / "router-field-records.jsonl"
            ledger_path.mkdir(parents=True)
            state_path = claude_dir / ".bakeoff-digest-state"
            state_path.write_text('{"seen": 7}\n', encoding="utf-8")

            context = self.run_hook(tempdir)

            marker = json.loads(state_path.read_text(encoding="utf-8"))

        self.assertIn("MODEL ROUTER: ACTIVE", context)
        self.assertNotIn("BAKE-OFF:", context)
        self.assertEqual(marker, {"seen": 7})

    def test_ledger_count_advances_since_last_marker(self):
        with tempfile.TemporaryDirectory() as tempdir:
            records = [json.dumps({"unit_ref": "U%d" % index}) for index in range(3)]
            self.write_ledger(tempdir, records)

            first_context = self.run_hook(tempdir)
            second_context = self.run_hook(tempdir)

        self.assertIn("3 replay(s) since last check", first_context)
        self.assertIn("3 ledger record(s)", first_context)
        self.assertIn("0 replay(s) since last check", second_context)
        self.assertIn("3 ledger record(s)", second_context)

    def test_positive_numeric_margins_count_as_challenger_wins(self):
        with tempfile.TemporaryDirectory() as tempdir:
            records = [
                {"margin": 0.5},
                {"margin": 2},
                {"margin": 0},
                {"margin": -1},
                {"margin": "3"},
            ]
            self.write_ledger(tempdir, [json.dumps(record) for record in records])

            context = self.run_hook(tempdir)

        self.assertIn("2 challenger win(s) pending", context)
        self.assertIn("5 ledger record(s)", context)

    def test_malformed_ledger_line_is_skipped_without_breaking_hook(self):
        with tempfile.TemporaryDirectory() as tempdir:
            self.write_ledger(
                tempdir,
                [
                    json.dumps({"margin": 1}),
                    "{not valid json",
                    json.dumps({"margin": -1}),
                ],
            )

            context = self.run_hook(tempdir)

        self.assertIn("2 replay(s) since last check", context)
        self.assertIn("1 challenger win(s) pending", context)
        self.assertIn("2 ledger record(s)", context)


if __name__ == "__main__":
    unittest.main()
