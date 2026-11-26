import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "local-bench")
loader = importlib.machinery.SourceFileLoader("local_bench", TOOL)
spec = importlib.util.spec_from_loader("local_bench", loader)
lb = importlib.util.module_from_spec(spec)
loader.exec_module(lb)


def side(agreement, completion, total_seconds, load_seconds=0.0, n=20):
    return {"items": n, "agreed": agreement, "completed": completion,
            "wall_seconds": total_seconds, "load_seconds": load_seconds}


class GradeTest(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(lb.grade({"a": 1, "b": "x"}, '{"a": 1, "b": "x"}'))

    def test_int_and_float_compare_equal(self):
        self.assertTrue(lb.grade({"amount": 318.0}, '{"amount": 318}'))

    def test_fenced_json_with_prose(self):
        self.assertTrue(lb.grade({"a": None}, 'Sure:\n```json\n{"a": null}\n```'))

    def test_missing_key_fails(self):
        self.assertFalse(lb.grade({"a": 1, "b": 2}, '{"a": 1}'))

    def test_wrong_value_fails(self):
        self.assertFalse(lb.grade({"pii_types": ["email", "name"]}, '{"pii_types": ["name", "email"]}'))

    def test_bool_is_not_number(self):
        self.assertFalse(lb.grade({"n": 1}, '{"n": true}'))

    def test_malformed_fails(self):
        self.assertFalse(lb.grade({"a": 1}, "no json here"))

    def test_timeout_output_none_fails(self):
        self.assertFalse(lb.grade({"a": 1}, None))


class WinRuleTest(unittest.TestCase):
    def test_challenger_faster_and_equal_wins(self):
        self.assertTrue(lb.challenger_wins(side(18, 20, 400), side(18, 20, 200)))

    def test_one_less_agreement_loses_even_when_faster(self):
        self.assertFalse(lb.challenger_wins(side(18, 20, 400), side(17, 20, 100)))

    def test_lower_completion_loses(self):
        self.assertFalse(lb.challenger_wins(side(15, 20, 400), side(15, 19, 100)))

    def test_load_time_counts(self):
        self.assertFalse(lb.challenger_wins(side(18, 20, 200, load_seconds=0), side(18, 20, 150, load_seconds=60)))

    def test_equal_time_does_not_win(self):
        self.assertFalse(lb.challenger_wins(side(18, 20, 200), side(18, 20, 200)))

    def test_time_per_task(self):
        self.assertEqual(lb.time_per_task(side(0, 0, 90, load_seconds=10, n=20)), 5.0)


class FakeBackend:
    """Scripted stand-in for llocal: answers keyed by (model, prompt)."""

    def __init__(self, answers, warm="OK", version_sequence=("0.3.2", "0.3.2")):
        self.answers = answers
        self.warm = warm
        self.calls = []
        self.versions = list(version_sequence)

    def run_item(self, model, prompt, flags, timeout):
        self.calls.append(("run", model, prompt))
        if prompt == lb.WARMUP_PROMPT:
            return {"stdout": self.warm, "seconds": 3.0, "timed_out": False, "rc": 0, "speed": None}
        answer = self.answers.get((model, prompt))
        if answer == "ERROR":
            return {"stdout": None, "seconds": 0.1, "timed_out": False, "rc": 1, "speed": None}
        if answer == "TIMEOUT":
            return {"stdout": None, "seconds": timeout, "timed_out": True, "rc": None, "speed": None}
        return {"stdout": answer, "seconds": 1.0, "timed_out": False, "rc": 0,
                "speed": {"prefill": 100.0, "decode": 50.0}}

    def unload(self, backend):
        self.calls.append(("unload", backend))

    def magnitude_version(self):
        return self.versions.pop(0) if len(self.versions) > 1 else self.versions[0]

    def model_provenance(self, model):
        return {"model": model, "source": "test", "sha256": ["abc"]}


ITEMS = [
    {"id": "t-1", "prompt": "p1", "expected": {"a": 1}},
    {"id": "t-2", "prompt": "p2", "expected": {"a": 2}},
]

INC = "qwen3.5:35b-a3b-coding-nvfp4"
CHAL = "qwen3.8-flash-next:gguf:q2"


class RunSideTest(unittest.TestCase):
    def test_timeout_counts_as_incomplete_and_unloads_before_next_wave(self):
        backend = FakeBackend({(CHAL, "p1"): "TIMEOUT", (CHAL, "p2"): '{"a": 2}'})
        result = lb.run_side(backend, CHAL, ITEMS, workers=1, effort=None, cap=5)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["agreed"], 1)
        run_calls = [c for c in backend.calls if c[0] in ("run", "unload")]
        p1 = run_calls.index(("run", CHAL, "p1"))
        p2 = run_calls.index(("run", CHAL, "p2"))
        self.assertIn(("unload", "magnitude"), run_calls[p1:p2])

    def test_concurrent_wave_lets_sibling_finish(self):
        backend = FakeBackend({(CHAL, "p1"): "TIMEOUT", (CHAL, "p2"): '{"a": 2}'})
        result = lb.run_side(backend, CHAL, ITEMS, workers=2, effort=None, cap=5)
        self.assertEqual(result["agreed"], 1)
        self.assertEqual([r["id"] for r in result["per_item"]], ["t-1", "t-2"])

    def test_each_item_keeps_its_raw_output(self):
        backend = FakeBackend({(CHAL, "p1"): '{"a": 1}', (CHAL, "p2"): "TIMEOUT"})
        result = lb.run_side(backend, CHAL, ITEMS, workers=1, effort=None, cap=5)
        self.assertEqual(result["per_item"][0]["output"], '{"a": 1}')
        self.assertIsNone(result["per_item"][1]["output"])

    def test_errored_item_is_not_completed(self):
        backend = FakeBackend({(CHAL, "p1"): "ERROR", (CHAL, "p2"): '{"a": 2}'})
        result = lb.run_side(backend, CHAL, ITEMS, workers=1, effort=None, cap=5)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["per_item"][0]["rc"], 1)

    def test_empty_warmup_aborts_before_timing(self):
        backend = FakeBackend({}, warm="")
        with self.assertRaises(lb.BenchAbort):
            lb.run_side(backend, CHAL, ITEMS, workers=1, effort=None, cap=5)
        self.assertEqual([c for c in backend.calls if c[0] == "run" and c[2] != lb.WARMUP_PROMPT], [])


class BenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.results = os.path.join(self.tmp.name, "results")
        self.catalog = os.path.join(self.tmp.name, "LOCAL_MODELS.md")
        with open(self.catalog, "w") as f:
            f.write("# Local models\n\nIntro.\n\n## Local Model Inventory\n\n| a |\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_bench(self, backend, **kw):
        return lb.benchmark(backend, "batch-extraction", CHAL, ITEMS, incumbent=kw.get("incumbent"),
                            workers=1, effort=None, cap=5, results_dir=self.results,
                            catalog_path=self.catalog, control=kw.get("control"))

    def answers(self, inc_ok=True, chal_ok=True):
        return {(INC, "p1"): '{"a": 1}' if inc_ok else '{"a": 9}', (INC, "p2"): '{"a": 2}',
                (CHAL, "p1"): '{"a": 1}' if chal_ok else '{"a": 9}', (CHAL, "p2"): '{"a": 2}'}

    def test_unloads_both_before_warmup_and_between_sides(self):
        backend = FakeBackend(self.answers())
        self.run_bench(backend)
        calls = backend.calls
        first_run = next(i for i, c in enumerate(calls) if c[0] == "run")
        self.assertEqual(set(c for c in calls[:first_run]), {("unload", "ollama"), ("unload", "magnitude")})
        last_inc = max(i for i, c in enumerate(calls) if c[0] == "run" and c[1] == INC)
        first_chal = min(i for i, c in enumerate(calls) if c[0] == "run" and c[1] == CHAL)
        self.assertIn(("unload", "ollama"), calls[last_inc:first_chal])

    def test_default_incumbent_recorded(self):
        result = self.run_bench(FakeBackend(self.answers()))
        self.assertEqual(result["incumbent"]["model"], INC)

    def test_result_file_has_version_provenance_and_verdict(self):
        result = self.run_bench(FakeBackend(self.answers(chal_ok=False)))
        files = os.listdir(self.results)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.results, files[0])) as f:
            saved = json.load(f)
        self.assertEqual(saved["magnitude_version"], "0.3.2")
        self.assertEqual(saved["verdict"], "incumbent holds")
        self.assertEqual(saved, result)
        self.assertEqual(saved["challenger"]["provenance"]["sha256"], ["abc"])
        self.assertIn("first_item_seconds", saved["challenger"])

    def test_version_change_mid_run_is_invalid(self):
        result = self.run_bench(FakeBackend(self.answers(), version_sequence=("0.3.2", "0.3.3")))
        self.assertEqual(result["verdict"], "invalid")

    def test_catalog_gets_one_entry_and_nothing_else_changes(self):
        with open(self.catalog) as f:
            before = f.read()
        self.run_bench(FakeBackend(self.answers()))
        self.run_bench(FakeBackend(self.answers()))
        with open(self.catalog) as f:
            after = f.read()
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertEqual(after.count("## Benchmarked builds"), 1)
        self.assertEqual(after.count("| batch-extraction |"), 2)

    def test_fixtures_are_synthetic_so_every_run_declares_no_pii(self):
        backend = FakeBackend(self.answers())
        captured = []
        original = backend.run_item

        def spy(model, prompt, flags, timeout):
            captured.append(flags)
            return original(model, prompt, flags, timeout)
        backend.run_item = spy
        lb.benchmark(backend, "pii-classification", CHAL, ITEMS, incumbent=None, workers=1, effort=None,
                     cap=5, results_dir=self.results, catalog_path=self.catalog, control=None)
        self.assertTrue(all("--no-pii" in f and "--pii" not in f for f in captured))

    def test_unrecorded_run_writes_nothing(self):
        with open(self.catalog) as f:
            before = f.read()
        result = lb.benchmark(FakeBackend(self.answers()), "batch-extraction", CHAL, ITEMS, incumbent=None,
                              workers=1, effort=None, cap=5, results_dir=self.results,
                              catalog_path=self.catalog, control=None, record=False)
        self.assertIn(result["verdict"], ("challenger wins", "incumbent holds"))
        self.assertFalse(os.path.exists(self.results))
        with open(self.catalog) as f:
            self.assertEqual(f.read(), before)


    def test_fast_errors_cannot_win_on_time(self):
        answers = self.answers()
        answers[(CHAL, "p1")] = "ERROR"
        answers[(INC, "p1")] = '{"a": 9}'
        result = self.run_bench(FakeBackend(answers))
        self.assertEqual(result["challenger"]["completed"], 1)
        self.assertEqual(result["verdict"], "incumbent holds")

    def test_abort_still_unloads_both_backends(self):
        backend = FakeBackend(self.answers())
        original = backend.run_item

        def failing_warmup(model, prompt, flags, timeout):
            if model == CHAL and prompt == lb.WARMUP_PROMPT:
                return {"stdout": "", "seconds": 1.0, "timed_out": False, "rc": 0, "speed": None}
            return original(model, prompt, flags, timeout)
        backend.run_item = failing_warmup
        with self.assertRaises(lb.BenchAbort):
            self.run_bench(backend)
        tail = backend.calls[-2:]
        self.assertEqual(set(tail), {("unload", "ollama"), ("unload", "magnitude")})
        self.assertFalse(os.path.exists(self.results))

    def test_control_pair_runs_after_main_pair(self):
        ctrl_o, ctrl_m = "qwen3.6:35b-a3b", "local:qwen3.6-35b-a3b:0123456789ab"
        answers = self.answers()
        answers.update({(ctrl_o, "p1"): '{"a": 1}', (ctrl_o, "p2"): '{"a": 2}',
                        (ctrl_m, "p1"): '{"a": 1}', (ctrl_m, "p2"): '{"a": 2}'})
        backend = FakeBackend(answers)
        result = self.run_bench(backend, control=(ctrl_o, ctrl_m))
        self.assertEqual(result["control"]["ollama"]["model"], ctrl_o)
        self.assertEqual(result["control"]["magnitude"]["model"], ctrl_m)
        self.assertIn("engine_wins", result["control"])
        last_chal = max(i for i, c in enumerate(backend.calls) if c[0] == "run" and c[1] == CHAL)
        first_ctrl = min(i for i, c in enumerate(backend.calls) if c[0] == "run" and c[1] == ctrl_o)
        self.assertIn(("unload", "magnitude"), backend.calls[last_chal:first_ctrl])

    def test_no_control_recorded(self):
        result = self.run_bench(FakeBackend(self.answers()))
        self.assertEqual(result["control"], "no control available")


class SpeedContractTest(unittest.TestCase):
    def test_llocal_speed_line_parses(self):
        import contextlib
        import io
        for data, expect in (
            ({"timings": {"prompt_per_second": 226.515, "predicted_per_second": 64.9872}}, (226.515, 64.9872)),
            ({"timings": {"prompt_per_second": 1e6, "predicted_per_second": 2.5e-05}}, (1e6, 2.5e-05)),
        ):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                lb.llocal._report_speed("magnitude", CHAL, data)
            match = lb.SPEED_LINE.search(err.getvalue())
            self.assertIsNotNone(match, err.getvalue())
            self.assertAlmostEqual(float(match.group(1)), expect[0])
            self.assertAlmostEqual(float(match.group(2)), expect[1])


class LlocalBackendTest(unittest.TestCase):
    def test_runs_llocal_with_bench_env(self):
        import subprocess
        seen = {}

        def fake_run(argv, **kw):
            seen["env"] = kw.get("env") or {}
            return subprocess.CompletedProcess(argv, 0, "ok", "")
        backend = lb.LlocalBackend()
        orig = lb.subprocess.run
        lb.subprocess.run = fake_run
        try:
            backend.run_item(CHAL, "hi", ["--no-pii"], 5)
        finally:
            lb.subprocess.run = orig
        self.assertEqual(seen["env"].get("LLOCAL_BENCH"), "1")

    def _unload_after_timeout(self, resident):
        import subprocess
        calls = []

        def fake_run(argv, **kw):
            calls.append(argv)
            if argv[:1] == [lb.sys.executable] and "unload" in argv:
                return subprocess.CompletedProcess(argv, 0, "unloaded", "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        backend = lb.LlocalBackend()
        backend._timed_out = {"ollama": {INC}}
        orig_run, orig_res = lb.subprocess.run, lb.llocal._ollama_resident
        lb.subprocess.run = fake_run
        lb.llocal._ollama_resident = lambda: list(resident)
        try:
            backend.unload("ollama")
        finally:
            lb.subprocess.run, lb.llocal._ollama_resident = orig_run, orig_res
        return [c for c in calls if c[:1] == ["pkill"]]

    def test_pkill_only_when_runner_is_the_timed_out_model(self):
        self.assertEqual(len(self._unload_after_timeout([INC])), 1)

    def test_pkill_skipped_when_another_model_is_resident(self):
        self.assertEqual(self._unload_after_timeout([INC, "gpt-oss:20b"]), [])


if __name__ == "__main__":
    unittest.main()
