"""Tests for local-drift: reconcile the LOCAL_MODELS.md installed inventory
table against the models actually installed in Ollama. Detection only — the
reconciler never writes a file (mirrors the codex-drift contract)."""

import os
import tempfile
import unittest

from bin import model_staleness as ms


INSTALLED = [
    "qwen3.5:35b-a3b-coding-nvfp4",
    "llava:13b",
    "llava:latest",
    "phi4-mini:latest",
    "nomic-embed-text:latest",
]


def local_catalog(inventory=None, last_reconciled="2026-07-14"):
    """A LOCAL_MODELS.md fixture: an inventory table plus a separate candidate
    table (which must NOT be read as installed-listed models)."""
    if inventory is None:
        inventory = list(INSTALLED)
    rows = []
    for m in inventory:
        # deliberately seed other cells with backticked flags/paths that are
        # NOT model IDs, to prove the parser keys on the first cell only.
        rows.append(
            "| `%s` | LLM | batch; never cap with `--num-predict` "
            "| prod SQL via `/api/chat` | ❌ `--workers 1` | 1 GB |" % m
        )
    return (
        "---\n"
        "last_refreshed: 2026-06-25\n"
        "last_reconciled: %s\n"
        "staleness_days: 30\n"
        "---\n\n"
        "# Local Models\n\n"
        "## Local Model Inventory\n\n"
        "| Model | Type | Best for | Avoid | Parallel (`--workers`) | Size |\n"
        "|---|---|---|---|---|---|\n"
        "%s\n\n"
        "*Last reconciled with `llocal models`: %s.*\n\n"
        "## Candidate Models — NOT installed, available via `ollama pull`\n\n"
        "| Model (`ollama pull`) | Type | Size |\n"
        "|---|---|---|\n"
        "| `llama3.1:70b` | General | 40 GB |\n"
        % (last_reconciled, "\n".join(rows), last_reconciled)
    )


class LocalDriftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cat = os.path.join(self.tmp.name, "LOCAL_MODELS.md")

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text=None):
        with open(self.cat, "w") as f:
            f.write(text if text is not None else local_catalog())

    def test_no_drift_when_table_matches_installed(self):
        self._write()
        r = ms.local_drift(catalog_path=self.cat, installed=list(INSTALLED))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["missing_from_table"], [])
        self.assertEqual(r["stale_in_table"], [])
        self.assertEqual(r["proposed_edits"], [])

    def test_candidate_table_models_are_not_treated_as_listed(self):
        # llama3.1:70b appears only in the Candidate section, and is not installed.
        # It must NOT surface as stale_in_table (that section isn't the inventory).
        self._write()
        r = ms.local_drift(catalog_path=self.cat, installed=list(INSTALLED))
        self.assertNotIn("llama3.1:70b", r["listed"])
        self.assertEqual(r["stale_in_table"], [])

    def test_installed_but_absent_from_table_is_drift(self):
        # gpt-oss:120b was pulled but never added to the inventory table.
        self._write()
        r = ms.local_drift(
            catalog_path=self.cat,
            installed=list(INSTALLED) + ["gpt-oss:120b"],
        )
        self.assertEqual(r["status"], "drift")
        self.assertIn("gpt-oss:120b", r["missing_from_table"])
        self.assertTrue(
            any(e.get("action") == "add-row" and e.get("model") == "gpt-oss:120b"
                for e in r["proposed_edits"])
        )

    def test_table_lists_uninstalled_model_is_drift(self):
        # table row for a model that is no longer installed.
        self._write()
        r = ms.local_drift(
            catalog_path=self.cat,
            installed=[m for m in INSTALLED if m != "llava:13b"],
        )
        self.assertEqual(r["status"], "drift")
        self.assertIn("llava:13b", r["stale_in_table"])

    def test_latest_suffix_reconciles_both_directions(self):
        # LOAD-BEARING naming reconciliation for the Ollama source: a bare name in
        # the table and an explicit `:latest` from Ollama (or vice versa) are the
        # same model and must NOT read as drift.
        inv = ["phi4-mini", "llava:latest"]  # phi4-mini written WITHOUT :latest
        self._write(local_catalog(inventory=inv))
        r = ms.local_drift(
            catalog_path=self.cat,
            installed=["phi4-mini:latest", "llava"],  # llava WITHOUT :latest
        )
        self.assertEqual(r["missing_from_table"], [])
        self.assertEqual(r["stale_in_table"], [])
        self.assertEqual(r["status"], "ok")

    def test_never_writes_the_catalog(self):
        self._write()
        with open(self.cat) as f:
            before = f.read()
        ms.local_drift(catalog_path=self.cat, installed=list(INSTALLED) + ["gpt-oss:120b"])
        with open(self.cat) as f:
            self.assertEqual(f.read(), before)

    def test_unreadable_catalog_no_crash(self):
        missing = os.path.join(self.tmp.name, "does-not-exist.md")
        try:
            r = ms.local_drift(catalog_path=missing, installed=list(INSTALLED))
        except Exception as e:  # noqa: BLE001 - must not crash
            self.fail("local_drift raised on unreadable catalog: %r" % e)
        self.assertEqual(r["status"], "parse_error")
        self.assertEqual(r["proposed_edits"], [])

    def test_non_model_backticks_do_not_become_listed_models(self):
        # --num-predict / /api/chat / --workers appear in non-first cells; none of
        # them may be parsed as a listed model id.
        self._write()
        r = ms.local_drift(catalog_path=self.cat, installed=list(INSTALLED))
        for junk in ("--num-predict", "/api/chat", "--workers", "--workers 1"):
            self.assertNotIn(junk, r["listed"])


if __name__ == "__main__":
    unittest.main()
