"""Tests for the pre-publish leak check."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


LEAK_CHECK = Path(__file__).parents[1] / "scripts" / "leak-check.sh"


class LeakCheckTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        (self.repo / "scripts").mkdir()
        shutil.copy2(LEAK_CHECK, self.repo / "scripts" / "leak-check.sh")
        (self.repo / ".gitignore").write_text(
            "scripts/leak-terms.local.txt\ndocs/plans/\n",
            encoding="utf-8",
        )
        (self.repo / "scripts" / "leak-terms.local.txt").write_text(
            "acmesecret\nwidgetco\tALLOW:allowed.txt\n",
            encoding="utf-8",
        )
        self.run_command("git", "init", "-q")
        self.run_command("git", "config", "user.name", "Test User")
        self.run_command("git", "config", "user.email", "test@example.com")
        self.run_command("git", "add", ".gitignore")
        self.run_command("git", "commit", "-qm", "initialize fixture")

    def tearDown(self):
        self.tempdir.cleanup()

    def run_command(self, *args):
        return subprocess.run(
            args,
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def run_leak_check(self):
        return subprocess.run(
            ["bash", "scripts/leak-check.sh"],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, relative_path, contents):
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def assert_caught(self, result, expected_output):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(expected_output, result.stdout)
        self.assertIn("LEAK-CHECK: FAIL", result.stdout)

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LEAK-CHECK: PASS", result.stdout)

    def test_untracked_non_ignored_file_with_term_is_caught(self):
        self.write_file("manifest.txt", "token=acmesecret\n")

        result = self.run_leak_check()

        self.assert_caught(result, "TERM 'acmesecret' FOUND IN:")
        self.assertIn("manifest.txt", result.stdout)

    def test_tracked_file_with_term_is_caught(self):
        self.write_file("tracked.txt", "acmesecret\n")
        self.run_command("git", "add", "tracked.txt")
        self.run_command("git", "commit", "-qm", "add tracked fixture")

        result = self.run_leak_check()

        self.assert_caught(result, "TERM 'acmesecret' FOUND IN:")
        self.assertIn("tracked.txt", result.stdout)

    def test_staged_file_with_term_is_caught(self):
        self.write_file("staged.txt", "acmesecret\n")
        self.run_command("git", "add", "staged.txt")

        result = self.run_leak_check()

        self.assert_caught(result, "TERM 'acmesecret' FOUND IN:")
        self.assertIn("staged.txt", result.stdout)

    def test_term_in_allowlisted_path_passes(self):
        self.write_file("allowed.txt", "widgetco\n")

        result = self.run_leak_check()

        self.assert_pass(result)

    def test_gitignored_file_with_term_is_not_scanned(self):
        self.write_file("docs/plans/local.md", "acmesecret\n")

        result = self.run_leak_check()

        self.assert_pass(result)

    def test_untracked_file_with_absolute_users_path_is_caught(self):
        self.write_file("notes.txt", "/" + "Users/example/private\n")

        result = self.run_leak_check()

        self.assert_caught(result, "ABSOLUTE HOME PATHS:")
        self.assertIn("notes.txt", result.stdout)

    def test_clean_repo_passes(self):
        self.write_file("README.md", "Clean fixture.\n")

        result = self.run_leak_check()

        self.assert_pass(result)


if __name__ == "__main__":
    unittest.main()
