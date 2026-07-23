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


if __name__ == "__main__":
    unittest.main()
