"""Tests for the emit-only challenger-seeding proposal helper."""

import contextlib
import datetime
import io
import tempfile
import unittest
from pathlib import Path

from bin import challenger_seeding


POLICY = """\
# Model Routing Policy

## 2. Task-shape → executor table

| Task shape | Candidate executors (`★` = preferred) | Notes |
|---|---|---|
| batch-extraction (text/JSON) | qwen3.5 ★❓ | bulk work |
| adversarial / second-opinion review | claude-opus-4-8 ★❓ | review |
| mechanical-refactor | gpt-oss:20b ★❌ (n=2: 2 losses, last 2026-01-01) | refactor |
| huge-context sweep | haiku-scout ★✅ (n=3: 3 clean, last 2026-01-01) | read-only |

## 3. Cell format & flip thresholds
"""


class ChallengerSeedingTests(unittest.TestCase):
    def setUp(self):
        self.rows = challenger_seeding.parse_candidate_matrix(POLICY)
        self.today = datetime.date(2026, 7, 23)

    def test_new_model_with_matching_tag_proposes_seed_for_existing_row(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="phi4-mini:latest",
                task_fit_tags=frozenset({"batch-extraction"}),
                is_new=True,
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].target_shape, "batch-extraction (text/JSON)")
        self.assertEqual(proposals[0].model_id, "phi4-mini:latest")
        self.assertEqual(proposals[0].trigger, challenger_seeding.NEW_CATALOG_MODEL)
        self.assertEqual(
            proposals[0].paste_line,
            "batch-extraction (text/JSON) | phi4-mini:latest ❓ | "
            "new catalog model matches task-fit tag",
        )

    def test_canonical_key_match_prevents_duplicate_candidate(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="claude-4.8-opus",
                task_fit_tags=frozenset({"adversarial / second-opinion review"}),
                is_new=True,
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(proposals, [])

    def test_plausible_untested_model_proposes_seed(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="phi4-mini:latest",
                task_fit_tags=frozenset({"batch-extraction"}),
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].trigger, challenger_seeding.PLAUSIBLE_UNTESTED)

    def test_unversioned_local_family_alias_prevents_duplicate(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="qwen3.5:35b-a3b-coding-nvfp4",
                task_fit_tags=frozenset({"batch-extraction"}),
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(proposals, [])

    def test_stale_verified_candidate_reopens_but_recent_one_is_silent(self):
        catalog = [
            challenger_seeding.CatalogModel(
                model_id="haiku-scout",
                task_fit_tags=frozenset({"huge-context sweep"}),
            )
        ]

        stale = challenger_seeding.propose_seeds(
            catalog, self.rows, today=self.today, staleness_days=90
        )
        recent_rows = challenger_seeding.parse_candidate_matrix(
            POLICY.replace(
                "last 2026-01-01) | read-only",
                "last 2026-07-01) | read-only",
            )
        )
        recent_cell = challenger_seeding.propose_seeds(
            catalog, recent_rows, today=self.today, staleness_days=90
        )
        recent_ledger = challenger_seeding.propose_seeds(
            catalog,
            self.rows,
            today=self.today,
            staleness_days=90,
            ledger_recency={
                ("huge-context sweep", "haiku-scout"): datetime.date(2026, 7, 1)
            },
        )

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].trigger, challenger_seeding.STALE_VERIFIED)
        self.assertEqual(recent_cell, [])
        self.assertEqual(recent_ledger, [])

    def test_materially_changed_failed_candidate_proposes_new_version_retry(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="gpt-oss:21b",
                task_fit_tags=frozenset({"mechanical-refactor"}),
                new_version_of="gpt-oss:20b",
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].target_shape, "mechanical-refactor")
        self.assertEqual(proposals[0].model_id, "gpt-oss:21b")
        self.assertEqual(
            proposals[0].trigger, challenger_seeding.MATERIALLY_CHANGED_RETRY
        )

    def test_new_model_without_matching_shape_is_silent(self):
        catalogs = [
            challenger_seeding.CatalogModel(
                model_id="nomic-embed-text:latest",
                task_fit_tags=frozenset({"embedding-index"}),
                is_new=True,
            )
        ]

        proposals = challenger_seeding.propose_seeds(
            catalogs, self.rows, today=self.today
        )

        self.assertEqual(proposals, [])

    def test_main_emits_without_modifying_policy(self):
        repo = Path(__file__).parents[1]
        self.assertTrue((repo / "templates" / "ROUTING_POLICY.md").is_file())
        with tempfile.TemporaryDirectory() as tempdir:
            catalog_dir = Path(tempdir)
            policy = catalog_dir / "ROUTING_POLICY.md"
            policy.write_text(POLICY, encoding="utf-8")
            (catalog_dir / "LOCAL_MODELS.md").write_text(
                "| Model | Type | Best for | Avoid | Parallel | Size |\n"
                "|---|---|---|---|---|---|\n"
                "| `phi4-mini:latest` | text | batch extraction | none | yes | 2GB |\n",
                encoding="utf-8",
            )
            before = policy.read_bytes()
            before_mtime = policy.stat().st_mtime_ns

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = challenger_seeding.main(
                    [
                        "--catalog-dir",
                        str(catalog_dir),
                        "--today",
                        "2026-07-23",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertIn("phi4-mini:latest ❓", output.getvalue())
            self.assertEqual(policy.read_bytes(), before)
            self.assertEqual(policy.stat().st_mtime_ns, before_mtime)


if __name__ == "__main__":
    unittest.main()
