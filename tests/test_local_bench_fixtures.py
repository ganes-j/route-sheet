import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bench import gen_synthetic_pii


FIXTURES = os.path.join(ROOT, "bench", "fixtures")
PII_TYPES = {"name", "email", "phone", "ssn", "address", "dob", "card"}
PHONE_PATTERN = re.compile(r"\b(?:\d{3}-\d{3}-\d{4}|555-\d{4})\b")
SAFE_PHONE_PATTERN = re.compile(r"555-01\d{2}")
TEST_CARDS = {"4111111111111111", "5555555555554444"}


def load_jsonl(name):
    path = os.path.join(FIXTURES, name)
    with open(path, encoding="utf-8") as fixture_file:
        return [json.loads(line) for line in fixture_file if line.strip()]


class LocalBenchFixtureTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_committed_fixture(self):
        first = gen_synthetic_pii.generate_items()
        second = gen_synthetic_pii.generate_items()
        self.assertEqual(first, second)
        self.assertEqual(first, load_jsonl("pii-classification.jsonl"))

    def test_fixture_shape_ids_and_counts(self):
        for name in ("batch-extraction.jsonl", "pii-classification.jsonl"):
            with self.subTest(name=name):
                items = load_jsonl(name)
                self.assertGreaterEqual(len(items), 18)
                self.assertLessEqual(len(items), 25)
                self.assertTrue(all(set(item) == {"id", "prompt", "expected"} for item in items))
                self.assertTrue(all(isinstance(item["prompt"], str) for item in items))
                self.assertTrue(all(isinstance(item["expected"], dict) for item in items))
                self.assertTrue(
                    all("only a JSON object with exactly the keys" in item["prompt"] for item in items)
                )
                self.assertTrue(
                    all(
                        all(key in item["prompt"] for key in item["expected"])
                        for item in items
                    )
                )
                self.assertTrue(
                    all(
                        all(not isinstance(value, dict) for value in item["expected"].values())
                        for item in items
                    )
                )
                ids = [item["id"] for item in items]
                self.assertEqual(len(ids), len(set(ids)))

    def test_pii_labels_use_sorted_vocabulary_and_match_boolean(self):
        for item in load_jsonl("pii-classification.jsonl"):
            expected = item["expected"]
            self.assertEqual(set(expected), {"contains_pii", "pii_types"})
            self.assertIs(type(expected["contains_pii"]), bool)
            self.assertEqual(expected["pii_types"], sorted(expected["pii_types"]))
            self.assertTrue(set(expected["pii_types"]).issubset(PII_TYPES))
            self.assertEqual(expected["contains_pii"], bool(expected["pii_types"]))

    def test_pii_positive_ratio_is_balanced(self):
        items = load_jsonl("pii-classification.jsonl")
        positives = sum(item["expected"]["contains_pii"] for item in items)
        ratio = positives / len(items)
        self.assertGreaterEqual(ratio, 0.4)
        self.assertLessEqual(ratio, 0.6)

    def test_synthetic_identifiers_stay_in_safe_ranges(self):
        text = "\n".join(item["prompt"] for item in load_jsonl("pii-classification.jsonl"))
        ssns = re.findall(r"\b\d{3}-\d{2}-\d{4}\b", text)
        phones = PHONE_PATTERN.findall(text)
        emails = re.findall(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", text)
        cards = re.findall(r"\b(?:\d[ -]?){15}\d\b", text)
        self.assertTrue(ssns)
        self.assertTrue(phones)
        self.assertTrue(emails)
        self.assertTrue(cards)
        self.assertTrue(all(ssn.startswith("9") for ssn in ssns))
        self.assertTrue(all(SAFE_PHONE_PATTERN.fullmatch(phone) for phone in phones))
        self.assertTrue(all(domain in {"example.com", "example.org", "example.net"} for domain in emails))
        self.assertTrue(all(re.sub(r"[ -]", "", card) in TEST_CARDS for card in cards))

    def test_phone_guard_detects_and_rejects_area_coded_values(self):
        phone = PHONE_PATTERN.search("Call 212-555-0100").group()
        self.assertIsNone(SAFE_PHONE_PATTERN.fullmatch(phone))


if __name__ == "__main__":
    unittest.main()
