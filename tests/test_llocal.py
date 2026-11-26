"""Integration tests for the extensionless bin/llocal script."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "llocal")


def load_llocal(module_name):
    loader = importlib.machinery.SourceFileLoader(module_name, TOOL)
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


llocal = load_llocal("llocal_test_module")


class FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        with self.server.request_lock:
            self.server.requests.append((self.path, None))
        status, response = self.server.responder(self.path, None)
        encoded = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        with self.server.request_lock:
            self.server.requests.append((self.path, body))
        status, response = self.server.responder(self.path, body)
        encoded = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format, *_args):
        pass


@contextlib.contextmanager
def fake_server(responder):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    server.responder = responder
    server.requests = []
    server.request_lock = threading.Lock()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@contextlib.contextmanager
def fake_magnitude_server(responder):
    with fake_server(responder) as server, mock.patch.object(
        llocal, "MAGNITUDE_BASE_URL", f"http://127.0.0.1:{server.server_port}/inference/v1"
    ):
        yield server


def magnitude_response(content="magnitude answer", timings=True):
    response = {"choices": [{"message": {"content": content}}]}
    if timings:
        response["timings"] = {"prompt_per_second": 12.5, "predicted_per_second": 34.75}
    return response


def ollama_response(content="ollama answer"):
    return {
        "message": {"content": content},
        "prompt_eval_count": 10,
        "prompt_eval_duration": 2_000_000_000,
        "eval_count": 20,
        "eval_duration": 1_000_000_000,
    }


class LlocalTest(unittest.TestCase):
    def setUp(self):
        for name, stub in (("_check_magnitude_trust", lambda _pii: None),
                           ("_free_other_backend", lambda _backend: None)):
            patcher = mock.patch.object(llocal, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *args, stdin=""):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = 0
        with mock.patch.object(sys, "argv", [TOOL, *args]), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                llocal.main()
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 1
                if isinstance(exc.code, str):
                    print(exc.code, file=sys.stderr)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_magnitude_run_prints_content_and_speed(self):
        with fake_magnitude_server(lambda _path, _body: (200, magnitude_response())) as server:
            code, stdout, stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii",
                "--system", "be terse", "--temp", "0.25", "--num-predict", "12"
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "magnitude answer\n")
        self.assertEqual(
            stderr,
            "llocal: magnitude qwen3.8-flash-next:gguf:q2 prefill 12.5 tok/s, decode 34.75 tok/s\n",
        )
        self.assertEqual(server.requests[0][0], "/inference/v1/chat/completions")
        self.assertEqual(
            server.requests[0][1],
            {
                "model": "qwen3.8-flash-next:gguf:q2",
                "messages": [
                    {"role": "system", "content": "be terse"},
                    {"role": "user", "content": "hello"},
                ],
                "stream": False,
                "temperature": 0.25,
                "max_tokens": 12,
            },
        )

    def test_magnitude_batch_returns_three_results_in_order(self):
        def respond(_path, body):
            return 200, magnitude_response(body["messages"][-1]["content"])

        with tempfile.NamedTemporaryFile("w", delete=False) as batch:
            batch.write('"first"\n{"id":"two","prompt":"second"}\n"third"\n')
            batch_path = batch.name
        self.addCleanup(lambda: os.unlink(batch_path))

        with fake_magnitude_server(respond):
            code, stdout, stderr = self.run_cli(
                "batch", "qwen3.8-flash-next:gguf:q2", batch_path, "--no-pii", "--workers", "2"
            )

        self.assertEqual(code, 0)
        self.assertEqual(
            [json.loads(line) for line in stdout.splitlines()],
            [
                {"id": 0, "out": "first"},
                {"id": "two", "out": "second"},
                {"id": 2, "out": "third"},
            ],
        )
        speed = "llocal: magnitude qwen3.8-flash-next:gguf:q2 prefill 12.5 tok/s, decode 34.75 tok/s\n"
        self.assertEqual(stderr.count(speed), 3)
        self.assertTrue(stderr.endswith("llocal batch: 3 ok, 0 errors (3 items)\n"))

    def test_magnitude_batch_without_pii_declaration_sends_no_request(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as batch:
            batch.write('"first"\n')
            batch_path = batch.name
        self.addCleanup(lambda: os.unlink(batch_path))

        with fake_magnitude_server(lambda _path, _body: (200, magnitude_response())) as server:
            code, _stdout, stderr = self.run_cli(
                "batch", "qwen3.8-flash-next:gguf:q2", batch_path
            )

        self.assertNotEqual(code, 0)
        self.assertIn("every Magnitude run must declare PII status", stderr)
        self.assertEqual(server.requests, [])

    def test_magnitude_batch_http_error_names_model_and_exits_nonzero(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as batch:
            batch.write('"first"\n')
            batch_path = batch.name
        self.addCleanup(lambda: os.unlink(batch_path))

        with fake_magnitude_server(lambda _path, _body: (404, {"error": "not found"})):
            code, stdout, stderr = self.run_cli(
                "batch", "qwen3.8-flash-next:gguf:q2", batch_path, "--no-pii"
            )

        self.assertEqual(code, 1)
        result = json.loads(stdout)
        self.assertIn("Magnitude", result["error"])
        self.assertIn("qwen3.8-flash-next:gguf:q2", result["error"])
        self.assertEqual(stderr, "llocal batch: 0 ok, 1 errors (1 items)\n")

    def test_ollama_run_payload_images_output_and_speed_are_unchanged(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as image:
            image.write(b"image bytes")
            image_path = image.name
        self.addCleanup(lambda: os.unlink(image_path))

        with fake_server(lambda _path, _body: (200, ollama_response())) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"):
            code, stdout, stderr = self.run_cli(
                "run", "llava:latest", "describe", "--image", image_path,
                "--system", "be terse", "--json", "json", "--temp", "0.2", "--num-predict", "9"
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "ollama answer\n")
        self.assertEqual(stderr, "llocal: ollama llava:latest prefill 5 tok/s, decode 20 tok/s\n")
        self.assertEqual(server.requests[0][0], "/api/chat")
        self.assertEqual(
            server.requests[0][1],
            {
                "model": "llava:latest",
                "messages": [
                    {"role": "system", "content": "be terse"},
                    {
                        "role": "user",
                        "content": "describe",
                        "images": ["aW1hZ2UgYnl0ZXM="],
                    },
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2, "num_predict": 9},
            },
        )

    def test_model_id_shapes_resolve_without_a_server_call(self):
        self.assertEqual(llocal._backend_for_model("gpt-oss:20b"), "ollama")
        self.assertEqual(llocal._backend_for_model("qwen3.5:35b-a3b-coding-nvfp4"), "ollama")
        self.assertEqual(llocal._backend_for_model("llava:latest"), "ollama")
        self.assertEqual(llocal._backend_for_model("qwen3.8-flash-next:gguf:q2"), "magnitude")
        self.assertEqual(
            llocal._backend_for_model("local:nomic-embed-text-v1.5-f16:ba1e29ae64db"),
            "magnitude",
        )

    def test_magnitude_json_modes_map_to_response_format(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        with fake_magnitude_server(
            lambda _path, _body: (200, magnitude_response(timings=False))
        ) as server:
            first = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii", "--json", "json"
            )
            second = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii",
                "--json", json.dumps(schema)
            )

        self.assertEqual(first[0], 0)
        self.assertEqual(second[0], 0)
        self.assertEqual(server.requests[0][1]["response_format"], {"type": "json_object"})
        self.assertEqual(
            server.requests[1][1]["response_format"],
            {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}},
        )

    def test_magnitude_without_timings_prints_content_without_speed(self):
        with fake_magnitude_server(
            lambda _path, _body: (200, magnitude_response("answer only", timings=False))
        ):
            code, stdout, stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--pii"
            )

        self.assertEqual((code, stdout, stderr), (0, "answer only\n", ""))

    def test_magnitude_closed_port_names_backend_and_start_commands(self):
        # A bound but non-listening socket hangs on macOS instead of refusing; close it first.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with mock.patch.object(
            llocal, "MAGNITUDE_BASE_URL", f"http://127.0.0.1:{port}/inference/v1"
        ):
            code, _stdout, stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii"
            )

        self.assertNotEqual(code, 0)
        self.assertIn("Magnitude", stderr)
        self.assertIn("open the Magnitude app", stderr)
        self.assertIn("magnitude serve", stderr)

    def test_magnitude_404_names_model(self):
        with fake_magnitude_server(lambda _path, _body: (404, {"error": "not found"})):
            code, _stdout, stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii"
            )

        self.assertNotEqual(code, 0)
        self.assertIn("qwen3.8-flash-next:gguf:q2", stderr)
        self.assertIn("Magnitude", stderr)

    def test_magnitude_image_is_rejected_before_request(self):
        with fake_magnitude_server(lambda _path, _body: (200, magnitude_response())) as server:
            code, _stdout, stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii", "--image", "unused"
            )

        self.assertNotEqual(code, 0)
        self.assertIn("--image", stderr)
        self.assertEqual(server.requests, [])

    def test_ollama_host_does_not_override_magnitude_address(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "http://127.0.0.1:54321"}):
            fresh = load_llocal("llocal_fresh_module")

        self.assertEqual(fresh.HOST, "http://127.0.0.1:54321")
        self.assertEqual(fresh.MAGNITUDE_BASE_URL, "http://127.0.0.1:10100/inference/v1")

    def test_magnitude_requires_pii_declaration_but_ollama_does_not(self):
        with fake_magnitude_server(lambda _path, _body: (200, magnitude_response())) as magnitude:
            rejected = self.run_cli("run", "qwen3.8-flash-next:gguf:q2", "hello")
        self.assertNotEqual(rejected[0], 0)
        self.assertIn("every Magnitude run must declare PII status", rejected[2])
        self.assertEqual(magnitude.requests, [])

        with fake_server(lambda _path, _body: (200, ollama_response())) as ollama, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{ollama.server_port}"):
            accepted = self.run_cli("run", "gpt-oss:20b", "hello")
        self.assertEqual(accepted[0], 0)

    def test_pii_flags_are_mutually_exclusive(self):
        code, _stdout, stderr = self.run_cli(
            "run", "qwen3.8-flash-next:gguf:q2", "hello", "--pii", "--no-pii"
        )
        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", stderr)

    def test_reasoning_effort_is_sent_to_magnitude(self):
        with fake_magnitude_server(
            lambda _path, _body: (200, magnitude_response(timings=False))
        ) as server:
            code, _stdout, _stderr = self.run_cli(
                "run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii",
                "--reasoning-effort", "xhigh"
            )

        self.assertEqual(code, 0)
        self.assertEqual(server.requests[0][1]["reasoning_effort"], "xhigh")

    def test_reasoning_effort_is_rejected_for_ollama(self):
        with fake_server(lambda _path, _body: (200, ollama_response())) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"):
            code, _stdout, stderr = self.run_cli(
                "run", "gpt-oss:20b", "hello", "--reasoning-effort", "low"
            )

        self.assertNotEqual(code, 0)
        self.assertIn("--reasoning-effort", stderr)
        self.assertIn("Magnitude", stderr)
        self.assertEqual(server.requests, [])


def magnitude_models(*states):
    models = []
    for model_id, residency in states:
        acq = {"_tag": "Installed"}
        if residency:
            acq["residencyState"] = {"_tag": residency}
        models.append({"modelId": model_id, "acquisitionState": acq})
    return json.dumps({"models": models})


class FakeMagnitudeCli:
    """Records CLI calls; `lists` is the sequence of `models list --json` outputs to return."""

    def __init__(self, lists, available=True):
        self.lists = list(lists)
        self.calls = []
        self.available = available

    def __call__(self, args):
        self.calls.append(list(args))
        if not self.available:
            return None
        if args[:2] == ["models", "stop"]:
            return 0, "Stopped the active local model."
        if args[:3] == ["models", "list", "--json"]:
            out = self.lists[0] if len(self.lists) == 1 else self.lists.pop(0)
            return out if isinstance(out, tuple) else (0, out)
        raise AssertionError("unexpected magnitude call %r" % args)


class UnloadTest(unittest.TestCase):
    run_cli = LlocalTest.run_cli

    def ollama(self, resident_sequence):
        sequence = list(resident_sequence)

        def responder(path, _body):
            if path == "/api/ps":
                names = sequence[0] if len(sequence) == 1 else sequence.pop(0)
                return 200, {"models": [{"name": n} for n in names]}
            if path == "/api/generate":
                return 200, {"done": True}
            return 404, {}
        return responder

    def unload(self, *args, cli=None, ollama=None):
        cli = cli or FakeMagnitudeCli([magnitude_models()])
        with contextlib.ExitStack() as stack:
            if ollama is not None:
                server = stack.enter_context(fake_server(ollama))
                stack.enter_context(mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"))
            else:
                server = None
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                stack.enter_context(mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{port}"))
            stack.enter_context(mock.patch.object(llocal, "_magnitude_cli", cli))
            stack.enter_context(mock.patch.object(llocal, "UNLOAD_POLL_SECONDS", 0))
            code, stdout, stderr = self.run_cli("unload", *args)
        return code, stdout, stderr, server, cli

    def test_ollama_unloads_each_resident_model_and_rechecks(self):
        code, stdout, _err, server, _cli = self.unload(
            "--backend", "ollama", ollama=self.ollama([["phi4-mini:latest", "gpt-oss:20b"], []]))
        self.assertEqual(code, 0)
        posts = [(p, b) for p, b in server.requests if p == "/api/generate"]
        self.assertEqual(sorted(b["model"] for _p, b in posts), ["gpt-oss:20b", "phi4-mini:latest"])
        self.assertTrue(all(b["keep_alive"] == 0 for _p, b in posts))
        self.assertEqual(sum(1 for p, _b in server.requests if p == "/api/ps"), 2)
        self.assertIn("phi4-mini:latest", stdout)

    def test_magnitude_backend_stops_and_confirms(self):
        cli = FakeMagnitudeCli([
            magnitude_models(("qwen3.8-flash-next:gguf:q2", "Ready")),
            magnitude_models(("qwen3.8-flash-next:gguf:q2", "Stopped")),
        ])
        code, stdout, _err, _server, cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertEqual(code, 0)
        self.assertEqual(sum(1 for c in cli.calls if c[:2] == ["models", "stop"]), 1)
        self.assertIn("qwen3.8-flash-next:gguf:q2", stdout)

    def test_nothing_resident_anywhere(self):
        code, stdout, _err, server, cli = self.unload(ollama=self.ollama([[]]))
        self.assertEqual(code, 0)
        self.assertIn("nothing to unload", stdout)
        self.assertFalse(any(p == "/api/generate" for p, _b in server.requests))
        self.assertFalse(any(c[:2] == ["models", "stop"] for c in cli.calls))

    def test_ollama_down_still_unloads_magnitude(self):
        cli = FakeMagnitudeCli([
            magnitude_models(("qwen3.8-flash-next:gguf:q2", "Ready")),
            magnitude_models(("qwen3.8-flash-next:gguf:q2", "Stopped")),
        ])
        code, _out, _err, _server, cli = self.unload(cli=cli)
        self.assertEqual(code, 0)
        self.assertTrue(any(c[:2] == ["models", "stop"] for c in cli.calls))

    def test_magnitude_cli_missing_counts_as_clear(self):
        code, _out, _err, _server, _cli = self.unload(
            "--backend", "magnitude", cli=FakeMagnitudeCli([], available=False))
        self.assertEqual(code, 0)

    def test_ollama_model_still_resident_fails_naming_it(self):
        code, _out, stderr, _server, _cli = self.unload(
            "--backend", "ollama", ollama=self.ollama([["phi4-mini:latest"]]))
        self.assertNotEqual(code, 0)
        self.assertIn("phi4-mini:latest", stderr)

    def test_magnitude_model_still_resident_fails_naming_it(self):
        cli = FakeMagnitudeCli([magnitude_models(("qwen3.8-flash-next:gguf:q2", "Ready"))])
        code, _out, stderr, _server, _cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertNotEqual(code, 0)
        self.assertIn("qwen3.8-flash-next:gguf:q2", stderr)

    def test_never_loaded_model_is_not_resident(self):
        cli = FakeMagnitudeCli([magnitude_models(("deepseek-v4.1-flash:gguf:iq2-xxs", "Unloaded"),
                                                 ("qwen3.8-flash-next:gguf:q2", "Stopped"))])
        code, stdout, _err, _server, cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertEqual(code, 0)
        self.assertIn("nothing to unload", stdout)
        self.assertFalse(any(c[:2] == ["models", "stop"] for c in cli.calls))

    def test_unknown_residency_tag_counts_as_resident(self):
        cli = FakeMagnitudeCli([magnitude_models(("qwen3.8-flash-next:gguf:q2", "Warming"))])
        code, _out, stderr, _server, _cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertNotEqual(code, 0)
        self.assertIn("qwen3.8-flash-next:gguf:q2", stderr)

    def test_magnitude_cli_failure_is_not_success(self):
        cli = FakeMagnitudeCli([(1, "")])
        code, _out, stderr, _server, _cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertNotEqual(code, 0)
        self.assertIn("cannot read", stderr)

    def test_magnitude_invalid_json_is_not_success(self):
        cli = FakeMagnitudeCli([(0, "not json")])
        code, _out, stderr, _server, _cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertNotEqual(code, 0)
        self.assertIn("cannot read", stderr)

    def test_magnitude_cli_failing_mid_poll_is_not_success(self):
        cli = FakeMagnitudeCli([magnitude_models(("qwen3.8-flash-next:gguf:q2", "Ready")), (1, "")])
        code, _out, stderr, _server, _cli = self.unload("--backend", "magnitude", cli=cli)
        self.assertNotEqual(code, 0)
        self.assertIn("qwen3.8-flash-next:gguf:q2", stderr)

    def test_ollama_polls_until_model_leaves(self):
        code, stdout, _err, _server, _cli = self.unload(
            "--backend", "ollama",
            ollama=self.ollama([["phi4-mini:latest"], ["phi4-mini:latest"], ["phi4-mini:latest"], []]))
        self.assertEqual(code, 0)
        self.assertIn("phi4-mini:latest", stdout)

    def test_ollama_ps_error_is_not_success(self):
        def responder(path, _body):
            return (500, {"error": "boom"}) if path == "/api/ps" else (200, {})
        code, _out, stderr, _server, _cli = self.unload("--backend", "ollama", ollama=responder)
        self.assertNotEqual(code, 0)
        self.assertIn("cannot read", stderr)


class GateTest(unittest.TestCase):
    run_cli = LlocalTest.run_cli

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.egress = os.path.join(self.tmp.name, "magnitude-egress.json")
        self.config = os.path.join(self.tmp.name, "config.json")
        self.results = os.path.join(self.tmp.name, "results")
        os.makedirs(self.results)
        self.version = "0.3.2"
        self.listeners = ["127.0.0.1"]
        self.write_egress()
        self.write_bench("0.3.2")

    def tearDown(self):
        self.tmp.cleanup()

    def write_egress(self, result="pass", version="0.3.2", expires="2099-01-01T00:00:00+00:00"):
        with open(self.egress, "w") as f:
            json.dump({"result": result, "magnitude_version": version, "expires_at": expires}, f)

    def write_bench(self, version, name="2026-11-25T10-00-00.json", challenger_backend="magnitude"):
        with open(os.path.join(self.results, name), "w") as f:
            json.dump({"magnitude_version": version, "challenger": {"backend": challenger_backend}}, f)

    def cli(self, args):
        if args == ["--version"]:
            return 0, self.version + "\n"
        raise AssertionError("unexpected magnitude call %r" % args)

    def run_gated(self, *flags, model="qwen3.8-flash-next:gguf:q2"):
        with fake_magnitude_server(lambda _p, _b: (200, magnitude_response("gated ok"))) as server, \
                mock.patch.object(llocal, "EGRESS_STATE", self.egress), \
                mock.patch.object(llocal, "MAGNITUDE_CONFIG", self.config), \
                mock.patch.object(llocal, "BENCH_RESULTS_DIR", self.results), \
                mock.patch.object(llocal, "_magnitude_cli", self.cli), \
                mock.patch.object(llocal, "_magnitude_listeners",
                                  lambda: None if self.listeners is None else list(self.listeners)):
            code, stdout, stderr = self.run_cli("run", model, "hello", *flags)
        return code, stdout, stderr, server

    def assert_refused(self, needle):
        code, _out, stderr, server = self.run_gated("--pii")
        self.assertNotEqual(code, 0)
        self.assertIn(needle, stderr)
        self.assertEqual(server.requests, [])

    def test_all_gates_hold_pii_run_proceeds(self):
        code, stdout, _err, server = self.run_gated("--pii")
        self.assertEqual((code, stdout), (0, "gated ok\n"))
        self.assertEqual(len(server.requests), 1)

    def test_no_egress_record_refused(self):
        os.unlink(self.egress)
        self.assert_refused("magnitude-egress-check")

    def test_failed_egress_record_refused(self):
        self.write_egress(result="fail")
        self.assert_refused("magnitude-egress-check")

    def test_expired_egress_record_refused(self):
        self.write_egress(expires="2020-01-01T00:00:00+00:00")
        self.assert_refused("expired")

    def test_egress_version_mismatch_refused(self):
        self.write_egress(version="0.3.1")
        self.assert_refused("0.3.1")

    def test_benchmark_version_mismatch_refuses_pii_and_warns_otherwise(self):
        self.write_bench("0.3.1", name="2026-11-25T11-00-00.json")
        self.assert_refused("benchmark")
        code, stdout, stderr, _server = self.run_gated("--no-pii")
        self.assertEqual((code, stdout), (0, "gated ok\n"))
        self.assertIn("0.3.1", stderr)

    def test_latest_benchmark_wins(self):
        self.write_bench("0.3.1", name="2026-11-24T10-00-00.json")
        code, _out, _err, _server = self.run_gated("--pii")
        self.assertEqual(code, 0)

    def test_no_benchmark_refuses_pii_and_warns_otherwise(self):
        for name in os.listdir(self.results):
            os.unlink(os.path.join(self.results, name))
        self.assert_refused("benchmark")
        code, _out, stderr, _server = self.run_gated("--no-pii")
        self.assertEqual(code, 0)
        self.assertIn("benchmark", stderr)

    def test_network_enabled_refused(self):
        with open(self.config, "w") as f:
            json.dump({"network": {"enabled": True}}, f)
        self.assert_refused("network")

    def test_config_without_network_key_is_off(self):
        with open(self.config, "w") as f:
            json.dump({"onboarding": {"done": True}}, f)
        code, _out, _err, _server = self.run_gated("--pii")
        self.assertEqual(code, 0)

    def test_wildcard_listener_refused(self):
        self.listeners = ["127.0.0.1", "*"]
        self.assert_refused("10100")

    def test_ipv6_loopback_listener_allowed(self):
        self.listeners = ["127.0.0.1", "[::1]"]
        code, _out, _err, _server = self.run_gated("--pii")
        self.assertEqual(code, 0)

    def test_pii_ollama_run_never_reads_magnitude_state(self):
        def boom(*_a, **_k):
            raise AssertionError("Magnitude state read for an Ollama run")
        with fake_server(lambda _p, _b: (200, ollama_response())) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", boom), \
                mock.patch.object(llocal, "_magnitude_listeners", boom), \
                mock.patch.object(llocal, "_free_other_backend", lambda _b: None):
            code, stdout, _err = self.run_cli("run", "phi4-mini:latest", "hello", "--pii")
        self.assertEqual((code, stdout), (0, "ollama answer\n"))

    def test_listener_probe_failure_refuses(self):
        self.listeners = None
        self.assert_refused("cannot verify")

    def test_unparseable_config_refused(self):
        with open(self.config, "w") as f:
            f.write("{not json")
        self.assert_refused("cannot read")

    def test_ollama_only_benchmark_does_not_count(self):
        for name in os.listdir(self.results):
            os.unlink(os.path.join(self.results, name))
        self.write_bench("0.3.2", challenger_backend="ollama")
        self.assert_refused("benchmark")

    def test_egress_refusal_tells_agent_to_ask_the_user(self):
        os.unlink(self.egress)
        code, _out, stderr, _server = self.run_gated("--pii")
        self.assertNotEqual(code, 0)
        self.assertIn("ask the user", stderr)

    def test_bench_env_skips_version_probe_for_no_pii(self):
        def no_cli(_args):
            raise AssertionError("version probed under LLOCAL_BENCH")
        for name in os.listdir(self.results):
            os.unlink(os.path.join(self.results, name))
        with mock.patch.dict(os.environ, {"LLOCAL_BENCH": "1"}), \
                mock.patch.object(llocal, "_magnitude_cli", no_cli), \
                fake_magnitude_server(lambda _p, _b: (200, magnitude_response("bench ok"))), \
                mock.patch.object(llocal, "BENCH_RESULTS_DIR", self.results):
            code, stdout, stderr = self.run_cli("run", "qwen3.8-flash-next:gguf:q2", "hello", "--no-pii")
        self.assertEqual((code, stdout), (0, "bench ok\n"))
        self.assertNotIn("warning", stderr)

    def test_bench_env_does_not_relax_pii(self):
        os.unlink(self.egress)
        with mock.patch.dict(os.environ, {"LLOCAL_BENCH": "1"}):
            self.assert_refused("egress")


class ListenerParseTest(unittest.TestCase):
    LSOF = ("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
            "magnitude 11370 j 9u IPv4 0x1 0t0 TCP 127.0.0.1:10100 (LISTEN)\n"
            "magnitude 11370 j 10u IPv6 0x2 0t0 TCP [::1]:10100 (LISTEN)\n"
            "magnitude 11370 j 11u IPv4 0x3 0t0 TCP *:10100 (LISTEN)\n")

    def probe(self, result=None, raises=None):
        def fake_run(*_a, **_k):
            if raises:
                raise raises
            return result
        with mock.patch.object(llocal.subprocess, "run", fake_run):
            return llocal._magnitude_listeners()

    def test_parses_hosts(self):
        import subprocess as sp
        hosts = self.probe(sp.CompletedProcess([], 0, self.LSOF, ""))
        self.assertEqual(hosts, ["127.0.0.1", "[::1]", "*"])

    def test_no_listener_is_empty(self):
        import subprocess as sp
        self.assertEqual(self.probe(sp.CompletedProcess([], 1, "", "")), [])

    def test_probe_error_is_unknown(self):
        import subprocess as sp
        self.assertIsNone(self.probe(raises=sp.TimeoutExpired("lsof", 15)))
        self.assertIsNone(self.probe(raises=OSError("no lsof")))

    def test_lsof_error_output_is_unknown(self):
        import subprocess as sp
        self.assertIsNone(self.probe(sp.CompletedProcess([], 1, "", "lsof: WARNING: something failed")))


class OllamaHintTest(unittest.TestCase):
    setUp = LlocalTest.setUp
    run_cli = LlocalTest.run_cli

    def test_ollama_404_hints_magnitude_id_format(self):
        with fake_server(lambda _p, _b: (404, {"error": "model 'qwen3.8-flash-next:q2' not found"})) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"):
            code, _out, stderr = self.run_cli("run", "qwen3.8-flash-next:q2", "hello")
        self.assertNotEqual(code, 0)
        self.assertIn("NAME:gguf:QUANT", stderr)


class ModelsAndMemoryTest(unittest.TestCase):
    run_cli = LlocalTest.run_cli

    def setUp(self):
        for name, value in (("_check_magnitude_trust", lambda _pii: None), ("UNLOAD_POLL_SECONDS", 0)):
            patcher = mock.patch.object(llocal, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def ollama(self, resident=()):
        def responder(path, _body):
            if path == "/api/tags":
                return 200, {"models": [{"name": "phi4-mini:latest", "size": 2.5e9,
                                         "details": {"family": "phi3", "parameter_size": "3.8B"}}]}
            if path == "/api/ps":
                return 200, {"models": [{"name": n} for n in resident]}
            if path == "/api/generate":
                return 200, {"done": True}
            return 200, ollama_response()
        return responder

    def cli(self, listing, calls):
        def run(args):
            calls.append(list(args))
            if args[:3] == ["models", "list", "--json"]:
                return listing
            if args[:2] == ["models", "stop"]:
                return 0, ""
            raise AssertionError(args)
        return run

    def test_models_table_shows_both_backends(self):
        calls = []
        listing = (0, magnitude_models(("qwen3.8-flash-next:gguf:q2", "Stopped")))
        with fake_server(self.ollama()) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", self.cli(listing, calls)):
            code, stdout, _err = self.run_cli("models")
        self.assertEqual(code, 0)
        self.assertRegex(stdout, r"phi4-mini:latest.*ollama")
        self.assertRegex(stdout, r"qwen3.8-flash-next:gguf:q2.*magnitude")

    def test_names_stay_ollama_only(self):
        calls = []
        listing = (0, magnitude_models(("qwen3.8-flash-next:gguf:q2", "Stopped")))
        with fake_server(self.ollama()) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", self.cli(listing, calls)):
            code, stdout, _err = self.run_cli("models", "--names")
        self.assertEqual((code, stdout), (0, "phi4-mini:latest\n"))

    def test_magnitude_down_still_lists_ollama_with_stderr_note(self):
        with fake_server(self.ollama()) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", self.cli((1, ""), [])):
            code, stdout, stderr = self.run_cli("models")
        self.assertEqual(code, 0)
        self.assertIn("phi4-mini:latest", stdout)
        self.assertNotIn("magnitude", stdout)
        self.assertIn("Magnitude", stderr)

    def test_magnitude_run_frees_resident_ollama_models_first(self):
        with fake_server(self.ollama(resident=["phi4-mini:latest"])) as oserver, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{oserver.server_port}"), \
                fake_magnitude_server(lambda _p, _b: (200, magnitude_response("m"))) as mserver:
            code, _out, _err = self.run_cli("run", "qwen3.8-flash-next:gguf:q2", "hi", "--no-pii")
        self.assertEqual(code, 0)
        unloads = [b for p, b in oserver.requests if p == "/api/generate"]
        self.assertEqual(unloads, [{"model": "phi4-mini:latest", "keep_alive": 0}])
        self.assertEqual(len(mserver.requests), 1)

    def test_ollama_run_stops_resident_magnitude_first(self):
        calls = []
        listing = (0, magnitude_models(("qwen3.8-flash-next:gguf:q2", "Ready")))
        with fake_server(self.ollama()) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", self.cli(listing, calls)):
            code, _out, _err = self.run_cli("run", "phi4-mini:latest", "hi")
        self.assertEqual(code, 0)
        self.assertIn(["models", "stop"], calls)

    def test_bench_env_skips_freeing(self):
        def boom(*_a, **_k):
            raise AssertionError("freed memory under LLOCAL_BENCH")
        with mock.patch.dict(os.environ, {"LLOCAL_BENCH": "1"}), \
                fake_server(self.ollama()) as server, \
                mock.patch.object(llocal, "HOST", f"http://127.0.0.1:{server.server_port}"), \
                mock.patch.object(llocal, "_magnitude_cli", boom):
            code, _out, _err = self.run_cli("run", "phi4-mini:latest", "hi")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
