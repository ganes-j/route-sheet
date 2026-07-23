"""Tests for the bake-off replay eligibility constraint layer."""

import tempfile
import unittest
from pathlib import Path

from bin import bakeoff_eligibility


class BakeoffEligibilityTests(unittest.TestCase):
    def clean_unit(self, **overrides):
        unit = {
            "executor": "codex-implementer",
            "verify_command": "python3 -m unittest tests/test_widget.py",
            "pii_bound": False,
            "shape": "impl-from-frozen-spec",
        }
        unit.update(overrides)
        return unit

    def test_pii_unit_keeps_only_local_challengers(self):
        unit = self.clean_unit(pii_bound=True)

        challengers = bakeoff_eligibility.filter_eligible_challengers(
            unit,
            [
                "codex-implementer",
                "llocal:qwen3.5",
                "codex-scout",
                "remote-vendor",
            ],
        )

        self.assertEqual(challengers, ["llocal:qwen3.5"])
        self.assertEqual(
            bakeoff_eligibility.check_bakeoff_eligibility(unit)[0],
            True,
        )

    def test_coordinator_and_never_delegate_units_are_ineligible(self):
        cases = [
            self.clean_unit(executor="coordinator"),
            self.clean_unit(shape="architecture"),
            self.clean_unit(shape="api-design"),
            self.clean_unit(shape="tiny edit (<20 lines)"),
            self.clean_unit(shape="session-scoped browser tools"),
            self.clean_unit(shape="destructive operations"),
            self.clean_unit(shape="github mutations"),
            self.clean_unit(shape="verification/review gate"),
        ]

        for unit in cases:
            with self.subTest(unit=unit):
                eligible, reason = (
                    bakeoff_eligibility.check_bakeoff_eligibility(unit)
                )
                self.assertFalse(eligible)
                self.assertIn("never-delegate", reason)

    def test_unit_without_verify_command_is_ineligible(self):
        eligible, reason = bakeoff_eligibility.check_bakeoff_eligibility(
            self.clean_unit(verify_command=None)
        )

        self.assertFalse(eligible)
        self.assertIn("verify-gate", reason)

    def test_nonlocal_service_url_in_verify_command_is_ineligible(self):
        eligible, reason = bakeoff_eligibility.check_bakeoff_eligibility(
            self.clean_unit(
                verify_command=(
                    "DATABASE_URL=postgresql://db.prod.example/app "
                    "python3 -m unittest tests/test_widget.py"
                )
            )
        )

        self.assertFalse(eligible)
        self.assertIn("verify-command-live-service", reason)

    def test_nonlocal_host_in_unit_env_is_ineligible(self):
        with tempfile.TemporaryDirectory() as tempdir:
            unit_dir = Path(tempdir)
            (unit_dir / ".env").write_text(
                "DATABASE_URL=postgresql://db.prod.example/app\n",
                encoding="utf-8",
            )

            eligible, reason = (
                bakeoff_eligibility.check_bakeoff_eligibility(
                    self.clean_unit(unit_dir=unit_dir)
                )
            )

        self.assertFalse(eligible)
        self.assertIn("unit-dir-host-scan", reason)

    def test_codex_cloud_exec_is_never_a_challenger(self):
        for pii_bound in (False, True):
            with self.subTest(pii_bound=pii_bound):
                challengers = (
                    bakeoff_eligibility.filter_eligible_challengers(
                        self.clean_unit(pii_bound=pii_bound),
                        [
                            "codex cloud exec",
                            "codex-cloud-exec",
                            "llocal:qwen3.5",
                        ],
                    )
                )
                self.assertNotIn("codex cloud exec", challengers)
                self.assertNotIn("codex-cloud-exec", challengers)

    def test_clean_frozen_spec_unit_is_eligible(self):
        with tempfile.TemporaryDirectory() as tempdir:
            unit_dir = Path(tempdir)
            (unit_dir / "dev.toml").write_text(
                'service_url = "http://localhost:8080/api"\n',
                encoding="utf-8",
            )

            eligible, reason = (
                bakeoff_eligibility.check_bakeoff_eligibility(
                    self.clean_unit(
                        unit_dir=unit_dir,
                        verify_command=(
                            "python3 verify.py --fixture file:///tmp/input "
                            "ghost=fixture"
                        ),
                    )
                )
            )

        self.assertTrue(eligible)
        self.assertIn("eligible", reason)

    def test_unclassifiable_unit_is_denied_by_default(self):
        eligible, reason = bakeoff_eligibility.check_bakeoff_eligibility(
            self.clean_unit(shape="unknown-shape")
        )

        self.assertFalse(eligible)
        self.assertIn("deny-by-default", reason)

    def test_candidate_executor_string_is_denied_as_unclassifiable(self):
        challengers = bakeoff_eligibility.filter_eligible_challengers(
            self.clean_unit(),
            "llocal:qwen3.5",
        )

        self.assertEqual(challengers, [])

    def test_config_symlink_is_denied_without_following_it(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            unit_dir = root / "unit"
            unit_dir.mkdir()
            external_env = root / "external.env"
            external_env.write_text(
                "DATABASE_URL=postgresql://db.prod.example/app\n",
                encoding="utf-8",
            )
            (unit_dir / ".env").symlink_to(external_env)

            eligible, reason = (
                bakeoff_eligibility.check_bakeoff_eligibility(
                    self.clean_unit(unit_dir=unit_dir)
                )
            )

        self.assertFalse(eligible)
        self.assertIn("symlink", reason)


if __name__ == "__main__":
    unittest.main()
