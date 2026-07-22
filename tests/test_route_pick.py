"""Tests for route_pick: deterministic candidate selection over the
ROUTING_POLICY.md §2 candidate-set matrix. These scenarios ARE the spec for
R3–R6 (auto-pick ★, verify-gate, challenger-competes, low-stakes scheduling).

pick(shape, verifiable, low_stakes, constraint_clean, matrix_text)
    -> (executor, is_bake_off_trial)
"""

import unittest

from bin import route_pick


def matrix(rows):
    """Build a minimal ROUTING_POLICY-shaped text with a §2 candidate table.
    `rows` is a list of (shape, candidates, notes)."""
    lines = [
        "# Model Routing Policy",
        "",
        "## 2. Task-shape → executor table",
        "",
        "| Task shape | Candidate executors (`★` = preferred) | Notes |",
        "|---|---|---|",
    ]
    for shape, cands, notes in rows:
        lines.append("| %s | %s | %s |" % (shape, cands, notes))
    lines += ["", "## 3. Cell format & flip thresholds", "", "(rules)"]
    return "\n".join(lines)


# Representative fixtures mirroring the real migrated matrix shapes.
SINGLE_VERIFIED = matrix([
    ("impl-from-frozen-spec",
     "codex-implementer ★✅ (n=6: 6 clean, last 2026-07-18, maintainer-signed)",
     "frozen spec"),
])
INCUMBENT_PLUS_CHALLENGER = matrix([
    ("batch-extraction (text/JSON)",
     "qwen3.5 ★✅ (n=2: 2 clean, last 2026-07-20) · gpt-oss:20b ❓",
     "llocal models"),
])
ALL_UNKNOWN = matrix([
    ("batch-extraction (text/JSON)",
     "qwen3.5 ★❓ · gpt-oss:20b ❓ · gpt-oss:120b ❓hq",
     "llocal models"),
])


class RoutePickTests(unittest.TestCase):
    # 1. Happy path — single ★✅ incumbent, verifiable unit.
    def test_happy_single_verified_incumbent(self):
        ex, trial = route_pick.pick(
            "impl-from-frozen-spec", verifiable=True, low_stakes=True,
            constraint_clean=True, matrix_text=SINGLE_VERIFIED)
        self.assertEqual(ex, "codex-implementer")
        self.assertFalse(trial)

    # 2. R5 challenger-competes — ★✅ incumbent AND ❓ challenger, low-stakes:
    #    the challenger runs even though a proven incumbent exists.
    def test_r5_challenger_competes_even_vs_verified_incumbent(self):
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=True,
            constraint_clean=True, matrix_text=INCUMBENT_PLUS_CHALLENGER)
        self.assertEqual(ex, "gpt-oss:20b")
        self.assertTrue(trial)

    # 3. R6 challenger-scheduling — same shape, HIGH-stakes: challenger waits,
    #    route to the ★ incumbent (which is ✅ → not a trial).
    def test_r6_high_stakes_routes_to_star_incumbent(self):
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=False,
            constraint_clean=True, matrix_text=INCUMBENT_PLUS_CHALLENGER)
        self.assertEqual(ex, "qwen3.5")
        self.assertFalse(trial)

    # 4. R4 verify-gate — no load-bearing verify command: never a write-worker
    #    or challenger; falls to coordinator, never a trial.
    def test_r4_verify_gate_never_write_worker_or_challenger(self):
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=False, low_stakes=True,
            constraint_clean=True, matrix_text=INCUMBENT_PLUS_CHALLENGER)
        self.assertEqual(ex, "coordinator")
        self.assertFalse(trial)
        self.assertNotIn(ex, ("qwen3.5", "gpt-oss:20b", "gpt-oss:120b"))

    # 5. R3 auto-pick incumbent-by-lean — all ❓, no ✅: ★ is the first-listed
    #    (incumbent-by-lean). Isolated with high-stakes so it routes to ★.
    def test_r3_incumbent_by_lean_when_no_verified(self):
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=False,
            constraint_clean=True, matrix_text=ALL_UNKNOWN)
        self.assertEqual(ex, "qwen3.5")
        self.assertTrue(trial)  # routing to a ❓ ★ is itself a bake-off trial

    # 6. R3 verified precedence — one ✅ and one ❓: ★ is the ✅ candidate even
    #    when it is not first-listed.
    def test_r3_verified_takes_star_over_incumbent_position(self):
        m = matrix([
            ("batch-extraction (text/JSON)",
             "qwen3.5 ❓ · gpt-oss:20b ✅ (n=2: 2 clean, last 2026-07-21)",
             "llocal models"),
        ])
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=False,
            constraint_clean=True, matrix_text=m)
        self.assertEqual(ex, "gpt-oss:20b")
        self.assertFalse(trial)

    # 7. R3 tiebreak — two ✅: pick the cheaper/smaller (size), NOT the higher-
    #    quality `hq` lane. Proves the tiebreak ignores any quality/benchmark
    #    signal and uses local+factual size only.
    def test_r3_tiebreak_cost_size_ignores_quality_signal(self):
        m = matrix([
            ("batch-extraction (text/JSON)",
             "gpt-oss:120b ✅hq (n=2: 2 clean, last 2026-07-21) · "
             "gpt-oss:20b ✅ (n=2: 2 clean, last 2026-07-21)",
             "llocal models"),
        ])
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=False,
            constraint_clean=True, matrix_text=m)
        self.assertEqual(ex, "gpt-oss:20b")  # 13 GB < 65 GB; hq is ignored
        self.assertFalse(trial)

    # 8. R6 precondition — constraint layer not clean: never a challenger trial;
    #    coordinator/local only per the passed flag.
    def test_constraint_not_clean_never_a_trial(self):
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=True,
            constraint_clean=False, matrix_text=INCUMBENT_PLUS_CHALLENGER)
        self.assertFalse(trial)
        self.assertNotIn(ex, ("qwen3.5", "gpt-oss:20b", "gpt-oss:120b"))
        self.assertEqual(ex, "coordinator")

    # 9. Parse safety — malformed / absent §2 row: safe default (coordinator),
    #    never raises.
    def test_parse_safety_absent_shape(self):
        ex, trial = route_pick.pick(
            "no-such-shape", verifiable=True, low_stakes=True,
            constraint_clean=True, matrix_text=ALL_UNKNOWN)
        self.assertEqual(ex, "coordinator")
        self.assertFalse(trial)

    # Word-boundary shape match — a truncated shape must NOT silently select a
    # longer row; only exact or boundary-delimited prefixes match.
    def test_shape_match_requires_word_boundary(self):
        # exact and boundary-prefix both resolve to the row
        for shape in ("batch-extraction (text/JSON)", "batch-extraction"):
            ex, _ = route_pick.pick(
                shape, verifiable=True, low_stakes=False,
                constraint_clean=True, matrix_text=ALL_UNKNOWN)
            self.assertEqual(ex, "qwen3.5", "shape %r should match" % shape)
        # truncated / abbreviated shapes must NOT match → safe coordinator
        for shape in ("batch", "batch-ext", "b"):
            ex, trial = route_pick.pick(
                shape, verifiable=True, low_stakes=False,
                constraint_clean=True, matrix_text=ALL_UNKNOWN)
            self.assertEqual((ex, trial), ("coordinator", False),
                             "truncated shape %r must not match" % shape)

    def test_parse_safety_garbage_text_no_exception(self):
        for junk in ("", "not a table at all", "## 2.\n| broken |\n", "|||"):
            try:
                ex, trial = route_pick.pick(
                    "batch-extraction (text/JSON)", verifiable=True,
                    low_stakes=True, constraint_clean=True, matrix_text=junk)
            except Exception as e:  # noqa: BLE001 - must not crash
                self.fail("pick raised on junk %r: %r" % (junk, e))
            self.assertEqual((ex, trial), ("coordinator", False))

    # Robustness — a ❌ ruled-out candidate is never selected as ★ or challenger.
    def test_ruled_out_candidate_excluded(self):
        m = matrix([
            ("batch-extraction (text/JSON)",
             "qwen3.5 ★❓ · gpt-oss:20b ❌ (n=3: ruled out, last 2026-07-21)",
             "llocal models"),
        ])
        ex, trial = route_pick.pick(
            "batch-extraction (text/JSON)", verifiable=True, low_stakes=True,
            constraint_clean=True, matrix_text=m)
        self.assertEqual(ex, "qwen3.5")  # no eligible ❓ challenger → the ★
        self.assertTrue(trial)

    # Read-only shape + no verify command: the read-only scout is fine (it has
    # no diff to re-check), still not a trial.
    def test_r4_read_only_shape_returns_scout_not_coordinator(self):
        m = matrix([
            ("adversarial / second-opinion review", "codex-scout ★❓",
             "read-only"),
        ])
        ex, trial = route_pick.pick(
            "adversarial / second-opinion review", verifiable=False,
            low_stakes=True, constraint_clean=True, matrix_text=m)
        self.assertEqual(ex, "codex-scout")
        self.assertFalse(trial)


if __name__ == "__main__":
    unittest.main()
