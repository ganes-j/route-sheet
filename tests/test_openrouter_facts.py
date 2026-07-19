"""Tests for the read-only OpenRouter factual catalog helper."""

import io
import json
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest import mock

from bin import openrouter_facts


def catalog_response(status=200):
    payload = {
        "data": [
            {
                "id": "openai/gpt-5.6-example",
                "context_length": 200000,
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "benchmark": {"score": 99},
            },
            {
                "id": "anthropic/claude-example",
                "context_length": 100000,
                "pricing": {"prompt": "0.000003", "completion": "0.000004"},
                "ranking": 1,
            },
            {
                "id": "google/gemini-example",
                "context_length": 300000,
                "pricing": {"prompt": "0.000005", "completion": "0.000006"},
            },
        ]
    }
    response = mock.MagicMock()
    response.status = status
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return response


class OpenRouterFactsTests(unittest.TestCase):
    @mock.patch("bin.openrouter_facts.urllib.request.urlopen")
    def test_happy_reconcile_contains_tracked_models_and_facts(self, urlopen):
        urlopen.return_value = catalog_response()

        reconcile = openrouter_facts.fetch_facts()

        self.assertEqual(len(reconcile), 2)
        self.assertEqual(
            reconcile[0],
            {
                "id": "openai/gpt-5.6-example",
                "context_length": 200000,
                "pricing_prompt": "0.000001",
                "pricing_completion": "0.000002",
            },
        )
        self.assertEqual(reconcile[1]["id"], "anthropic/claude-example")
        self.assertEqual(reconcile[1]["context_length"], 100000)
        self.assertEqual(reconcile[1]["pricing_prompt"], "0.000003")
        self.assertEqual(reconcile[1]["pricing_completion"], "0.000004")

    @mock.patch("bin.openrouter_facts.urllib.request.urlopen")
    def test_filter_excludes_untracked_vendor(self, urlopen):
        urlopen.return_value = catalog_response()

        reconcile = openrouter_facts.fetch_facts()

        self.assertNotIn("google/gemini-example", [item["id"] for item in reconcile])

    @mock.patch("bin.openrouter_facts.urllib.request.urlopen")
    def test_reconcile_is_factual_only(self, urlopen):
        urlopen.return_value = catalog_response()

        reconcile = openrouter_facts.fetch_facts()

        for item in reconcile:
            self.assertNotIn("benchmark", item)
            self.assertNotIn("ranking", item)
            self.assertEqual(
                set(item),
                {"id", "context_length", "pricing_prompt", "pricing_completion"},
            )

    @mock.patch("bin.openrouter_facts.urllib.request.urlopen")
    def test_unavailable_network_and_non_200_exit_zero(self, urlopen):
        for behavior in (
            urllib.error.URLError("offline"),
            catalog_response(status=503),
        ):
            with self.subTest(behavior=type(behavior).__name__):
                urlopen.reset_mock()
                if isinstance(behavior, Exception):
                    urlopen.side_effect = behavior
                    urlopen.return_value = mock.DEFAULT
                else:
                    urlopen.side_effect = None
                    urlopen.return_value = behavior
                output = io.StringIO()
                with redirect_stdout(output):
                    exit_code = openrouter_facts.main(["--json"])
                result = json.loads(output.getvalue())
                self.assertEqual(exit_code, 0)
                self.assertFalse(result["available"])
                self.assertTrue(result["reason"])

    @mock.patch("bin.openrouter_facts.urllib.request.urlopen")
    def test_read_only_opens_only_public_models_url(self, urlopen):
        urlopen.return_value = catalog_response()

        openrouter_facts.fetch_facts()

        urlopen.assert_called_once_with(openrouter_facts.MODELS_URL, timeout=10)
        self.assertEqual(
            urlopen.call_args.args[0], "https://openrouter.ai/api/v1/models"
        )


if __name__ == "__main__":
    unittest.main()
