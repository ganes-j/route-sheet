"""Tests for the field-record JSONL ledger."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


FIELD_RECORDS_PATH = Path(__file__).parents[1] / "bin" / "field_records.py"
SPEC = importlib.util.spec_from_file_location("field_records", FIELD_RECORDS_PATH)
field_records = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(field_records)


class FieldRecordTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tempdir.name) / "field-records.jsonl"

    def tearDown(self):
        self.tempdir.cleanup()

    def record(self, **overrides):
        record = {
            "unit_ref": "U1",
            "shape": "stdlib-python",
            "executor": "codex",
            "kind": "replay",
            "verify_pass": True,
            "margin": 0.25,
            "fix_rounds": 0,
            "base_commit": "abc123",
            "provenance": {"model_tag": "gpt-5"},
            "date": "2026-07-23",
        }
        record.update(overrides)
        return record

    def test_append_and_query_round_trip_with_all_filters(self):
        matching = self.record(unit_ref="U1")
        field_records.append_record(matching, self.ledger)
        field_records.append_record(
            self.record(
                unit_ref="U2",
                shape="shell",
                executor="ollama",
                kind="reverse-replay",
                date="2026-07-24",
            ),
            self.ledger,
        )

        result = field_records.query_records(
            self.ledger,
            shape="stdlib-python",
            executor="codex",
            kind="replay",
            date_from="2026-07-22",
            date_to="2026-07-23",
        )

        self.assertEqual(result.records, [matching])
        self.assertEqual(result.skipped_count, 0)
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), matching)

    def test_margin_less_real_record_is_valid_and_queryable(self):
        record = self.record(kind="real")
        del record["margin"]

        field_records.append_record(record, self.ledger)
        result = field_records.query_records(self.ledger, kind="real")

        self.assertEqual(result.records, [record])
        self.assertNotIn("margin", result.records[0])

    def test_negative_margin_on_verify_pass_record_round_trips(self):
        record = self.record(verify_pass=True, margin=-0.75)

        field_records.append_record(record, self.ledger)
        result = field_records.query_records(self.ledger)

        self.assertEqual(result.records[0]["margin"], -0.75)
        self.assertTrue(result.records[0]["verify_pass"])

    def test_missing_required_field_names_the_field(self):
        record = self.record()
        del record["base_commit"]

        with self.assertRaisesRegex(ValueError, r"missing required field: base_commit"):
            field_records.append_record(record, self.ledger)

        self.assertFalse(self.ledger.exists())

    def test_provenance_optional_keys_round_trip(self):
        minimal = self.record(
            unit_ref="minimal",
            provenance={"model_tag": "qwen3.5:9b"},
        )
        expanded = self.record(
            unit_ref="expanded",
            provenance={
                "model_tag": "gpt-5",
                "quantization": "q4_k_m",
                "judge_model": "gpt-5.1",
                "rubric_version": "v2",
            },
        )

        field_records.append_record(minimal, self.ledger)
        field_records.append_record(expanded, self.ledger)
        result = field_records.query_records(self.ledger)

        self.assertEqual(result.records, [minimal, expanded])

    def test_corrupt_mid_file_line_is_skipped_and_read_continues(self):
        first = self.record(unit_ref="first")
        last = self.record(unit_ref="last")
        field_records.append_record(first, self.ledger)
        with self.ledger.open("a", encoding="utf-8") as ledger:
            ledger.write("{not valid json}\n")
        field_records.append_record(last, self.ledger)

        result = field_records.query_records(self.ledger)

        self.assertEqual(result.records, [first, last])
        self.assertEqual(result.skipped_count, 1)

    def test_invalid_kind_and_out_of_range_margin_reject(self):
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            field_records.append_record(
                self.record(kind="simulation"),
                self.ledger,
            )
        with self.assertRaisesRegex(ValueError, "margin must be between -1.0 and 1.0"):
            field_records.append_record(
                self.record(margin=1.01),
                self.ledger,
            )


class ReplayBundleTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "bundles"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_bundle_writer_produces_documented_layout(self):
        result = field_records.write_bundle(
            self.root,
            "U4",
            base_commit="abc123",
            spec="Implement the runner.",
            verify_commands=["python3 -m unittest tests/test_bakeoff_grading.py"],
            first_shot_patch="diff --git a/x b/x\n",
        )

        self.assertTrue(result.written)
        self.assertFalse(result.margin_limited)
        self.assertIsNone(result.refused_reason)
        bundle = self.root / "U4"
        self.assertEqual(result.path, bundle)
        meta = json.loads((bundle / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["base_commit"], "abc123")
        self.assertEqual(
            meta["verify_commands"],
            ["python3 -m unittest tests/test_bakeoff_grading.py"],
        )
        self.assertFalse(meta["margin_limited"])
        self.assertEqual(
            (bundle / "spec.md").read_text(encoding="utf-8"),
            "Implement the runner.",
        )
        self.assertEqual(
            (bundle / "first_shot.patch").read_text(encoding="utf-8"),
            "diff --git a/x b/x\n",
        )

    def test_missing_first_shot_artifact_marks_margin_limited_not_rejected(self):
        result = field_records.write_bundle(
            self.root,
            "U7",
            base_commit="def456",
            spec="Trial unit, no incumbent diff.",
            verify_commands=["python3 -m unittest tests/test_route_pick.py"],
            first_shot_patch=None,
        )

        self.assertTrue(result.written)
        self.assertTrue(result.margin_limited)
        bundle = self.root / "U7"
        self.assertFalse((bundle / "first_shot.patch").exists())
        meta = json.loads((bundle / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(meta["margin_limited"])

    def test_secret_pattern_hit_refuses_bundle_write(self):
        # Assemble the credential-shaped URL at runtime so the literal never sits
        # in a tracked source line (leak-check.sh's structural gate would flag it);
        # the assembled string is still credential-shaped and tests detection.
        creds = "adm" + "in:secr" + "et"
        leaking_spec = f"see postgres://{creds}@db.prod.example.com:5432/main"
        result = field_records.write_bundle(
            self.root,
            "U9",
            base_commit="ghi789",
            spec=leaking_spec,
            verify_commands=["pytest"],
            first_shot_patch=None,
        )

        self.assertFalse(result.written)
        self.assertIsNotNone(result.refused_reason)
        self.assertIn("credential-shaped URL", result.refused_reason)
        self.assertFalse((self.root / "U9").exists())

    def test_traversal_unit_ref_is_refused(self):
        result = field_records.write_bundle(
            self.root,
            "../../tmp/evil",
            base_commit="abc",
            spec="x",
            verify_commands=["true"],
            first_shot_patch=None,
        )
        self.assertFalse(result.written)
        self.assertIn("unsafe bundle path component", result.refused_reason)
        self.assertFalse((self.root.parent / "tmp" / "evil").exists())

    def test_namespace_prevents_same_unit_ref_collision(self):
        a = field_records.write_bundle(
            self.root, "U1", base_commit="p1", spec="plan-one",
            verify_commands=["true"], first_shot_patch="patch-1\n",
            namespace="plan-alpha",
        )
        b = field_records.write_bundle(
            self.root, "U1", base_commit="p2", spec="plan-two",
            verify_commands=["true"], first_shot_patch="patch-2\n",
            namespace="plan-beta",
        )
        self.assertTrue(a.written and b.written)
        self.assertNotEqual(a.path, b.path)
        self.assertEqual((a.path / "spec.md").read_text(encoding="utf-8"), "plan-one")
        self.assertEqual((b.path / "spec.md").read_text(encoding="utf-8"), "plan-two")

    def test_recapture_without_first_shot_removes_stale_patch(self):
        first = field_records.write_bundle(
            self.root, "U4", base_commit="c1", spec="s",
            verify_commands=["true"], first_shot_patch="original\n",
        )
        self.assertTrue((first.path / "first_shot.patch").exists())
        again = field_records.write_bundle(
            self.root, "U4", base_commit="c2", spec="s",
            verify_commands=["true"], first_shot_patch=None,
        )
        self.assertTrue(again.margin_limited)
        self.assertFalse((again.path / "first_shot.patch").exists())


class OutcomeLineParserTests(unittest.TestCase):
    def test_parses_line_without_base_token(self):
        line = (
            "U2 · codex-implementer · PASS · re-check `pnpm test parser` green · "
            "0 fix rounds · 01JABCsession · 2026-07-20"
        )
        parsed = field_records.parse_outcome_line(line)

        self.assertEqual(parsed.unit_ref, "U2")
        self.assertEqual(parsed.executor, "codex-implementer")
        self.assertEqual(parsed.status, "PASS")
        self.assertEqual(parsed.date, "2026-07-20")
        self.assertIsNone(parsed.base_commit)

    def test_parses_line_with_trailing_base_token(self):
        line = (
            "- U2 · codex-implementer · PASS · re-check `pnpm test parser` green · "
            "0 fix rounds · 01JABCsession · 2026-07-20 · base:ba3f924"
        )
        parsed = field_records.parse_outcome_line(line)

        self.assertEqual(parsed.unit_ref, "U2")
        self.assertEqual(parsed.date, "2026-07-20")
        self.assertEqual(parsed.base_commit, "ba3f924")


if __name__ == "__main__":
    unittest.main()
