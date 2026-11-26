import importlib.machinery
import itertools
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "magnitude-egress-check")
loader = importlib.machinery.SourceFileLoader("mec", TOOL)
spec = importlib.util.spec_from_loader("mec", loader)
mec = importlib.util.module_from_spec(spec)
loader.exec_module(mec)


def done(stdout="", stderr="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout, stderr)


IDLE_MODELS = json.dumps({"models": [
    {"modelId": "qwen3.8-flash-next:gguf:q2", "acquisitionState": {"_tag": "Ready"}},
]})
DOWNLOADING_MODELS = json.dumps({"models": [
    {"modelId": "deepseek-v4.1-flash:gguf:iq2-xxs", "acquisitionState": {"_tag": "Installing"}},
]})

PS = (
    "  100     1 /Applications/Magnitude.app/Contents/MacOS/Magnitude\n"
    "  101   100 /Applications/Magnitude.app/Contents/Resources/magnitude-service\n"
    "  102   101 /opt/x/.magnitude/releases/bin/magnitude-inference\n"
    "  103   102 /opt/x/.magnitude/releases/bin/magnitude-inference --worker\n"
    "  200     1 /usr/bin/unrelated\n"
)

LSOF_HEADER = "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
LSOF_LOOPBACK = LSOF_HEADER + "magnitude 102 x 9u IPv4 0x1 0t0 TCP 127.0.0.1:10100->127.0.0.1:50000 (ESTABLISHED)\n"
LSOF_FOREIGN = LSOF_HEADER + "magnitude 102 x 9u IPv4 0x1 0t0 TCP 192.168.1.5:50001->54.225.198.112:443 (ESTABLISHED)\n"


def fake_run(models=IDLE_MODELS, update="Magnitude is up to date.", version="0.3.2"):
    def run(argv, timeout=60):
        if argv[-1] == "--version":
            return done(version + "\n") if version else done(rc=1)
        if argv[1:4] == ["models", "list", "--json"]:
            return done(models)
        if argv[1:3] == ["update", "status"]:
            return done(update)
        if argv[0] == "ps":
            return done(PS)
        raise AssertionError("unexpected command %r" % argv)
    return run


class ProcessTreeTest(unittest.TestCase):
    def test_collects_magnitude_descendants_only(self):
        self.assertEqual(mec.magnitude_pids(fake_run()), [100, 101, 102, 103])


class ActiveWorkTest(unittest.TestCase):
    def test_idle(self):
        self.assertEqual(mec.active_work(fake_run()), [])

    def test_download_in_progress(self):
        busy = mec.active_work(fake_run(models=DOWNLOADING_MODELS))
        self.assertEqual(busy, ["download: deepseek-v4.1-flash:gguf:iq2-xxs"])

    def test_ready_to_install_update_is_not_active(self):
        self.assertEqual(mec.active_work(fake_run(update="Magnitude 0.3.3 is ready to install.")), [])

    def test_update_downloading_is_active(self):
        busy = mec.active_work(fake_run(update="Downloading Magnitude 0.3.3 (40%)"))
        self.assertEqual(len(busy), 1)
        self.assertTrue(busy[0].startswith("update"))


class ForeignSocketTest(unittest.TestCase):
    def _sockets(self, lsof_out):
        return mec.foreign_sockets([102], lambda argv, timeout=60: done(lsof_out))

    def test_loopback_only(self):
        self.assertEqual(self._sockets(LSOF_LOOPBACK), [])

    def test_foreign_socket_named(self):
        hits = self._sockets(LSOF_FOREIGN)
        self.assertEqual(len(hits), 1)
        self.assertIn("54.225.198.112:443", hits[0][2])

    def test_ipv6_loopback(self):
        out = LSOF_HEADER + "magnitude 102 x 9u IPv6 0x1 0t0 TCP [::1]:10100->[::1]:50000 (ESTABLISHED)\n"
        self.assertEqual(self._sockets(out), [])

    def test_no_pids_no_call(self):
        self.assertEqual(mec.foreign_sockets([], lambda *a, **k: self.fail("lsof called")), [])

    def test_lsof_failure_is_unknown(self):
        def boom(argv, timeout=60):
            raise subprocess.TimeoutExpired(argv, timeout)
        self.assertIsNone(mec.foreign_sockets([102], boom))


class AtRestAndCaptureTest(unittest.TestCase):
    def test_canary_found_in_sqlite_but_not_in_models(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "chats.sqlite"), "wb") as f:
                f.write(b"xx EGRESS-CANARY-abc yy")
            os.makedirs(os.path.join(d, "models"))
            with open(os.path.join(d, "models", "weights.json"), "wb") as f:
                f.write(b"EGRESS-CANARY-abc")
            self.assertEqual(mec.scan_at_rest(["EGRESS-CANARY-abc"], d), [os.path.join(d, "chats.sqlite")])



PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a" + b"\x00" * 24


def fake_run_with(pcap, writer=True, pids_in_filter=("100", "101", "102", "103"), **kw):
    base = fake_run(**kw)
    tcpdump = ("  900     1 tcpdump -i pktap,all -k -U -w %s -Q %s not (host 127.0.0.1 or host ::1)\n"
               % (pcap, " or ".join("pid=" + p for p in pids_in_filter)))

    def run(argv, timeout=60):
        if argv[0] == "ps":
            return done(PS + (tcpdump if writer else ""))
        return base(argv, timeout)
    return run


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state", "magnitude-egress.json")
        self.pcap = os.path.join(self.tmp.name, "cap.pcapng")
        with open(self.pcap, "wb") as f:
            f.write(PCAPNG_MAGIC)
        self.at_rest = os.path.join(self.tmp.name, "home")
        os.makedirs(self.at_rest)
        self.fake_llocal = os.path.join(self.tmp.name, "llocal")
        with open(self.fake_llocal, "w") as f:
            f.write("print('ok')\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _main(self, run=None, polled=(0, [], 0), during=None, argv=None):
        run = run or fake_run_with(self.pcap)

        def fake_polling(*_a, **_k):
            if during:
                during()
            return polled
        orig = mec.run_with_polling
        mec.run_with_polling = fake_polling
        try:
            return mec.main(argv or ["--pcap", self.pcap, "--margin", "0", "--interval", "0"],
                            run=run, state_path=self.state, at_rest_root=self.at_rest, llocal=self.fake_llocal)
        finally:
            mec.run_with_polling = orig

    def state_result(self):
        with open(self.state) as f:
            return json.load(f)["result"]

    def test_no_pcap_prints_pid_scoped_command(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = mec.main([], run=fake_run(), state_path=self.state)
        self.assertEqual(rc, 2)
        self.assertIn("-Q", err.getvalue())
        self.assertIn("pid=102", err.getvalue())
        self.assertFalse(os.path.exists(self.state))

    def test_pass_when_capture_live_and_unchanged(self):
        self.assertEqual(self._main(), 0)
        self.assertEqual(self.state_result(), "pass")
        self.assertEqual(stat.S_IMODE(os.stat(self.state).st_mode), 0o600)

    def test_any_capture_growth_fails(self):
        def grow():
            with open(self.pcap, "ab") as f:
                f.write(b"\x06\x00\x00\x00packet")
        self.assertEqual(self._main(during=grow), 1)
        self.assertEqual(self.state_result(), "fail")

    def test_canary_in_new_capture_bytes_fails(self):
        orig = mec.uuid.uuid4

        class U:
            hex = "fixed"
        mec.uuid.uuid4 = lambda: U()

        def leak():
            with open(self.pcap, "ab") as f:
                f.write(b"EGRESS-CANARY-fixed")
        try:
            self.assertEqual(self._main(during=leak), 1)
        finally:
            mec.uuid.uuid4 = orig

    def test_empty_capture_with_live_writer_passes(self):
        # macOS tcpdump on pktap defers the pcapng header until the first matching packet,
        # so a clean capture stays at 0 bytes for its whole life.
        open(self.pcap, "wb").close()
        self.assertEqual(self._main(), 0)
        self.assertEqual(self.state_result(), "pass")

    def test_empty_capture_without_live_writer_exits_3(self):
        open(self.pcap, "wb").close()
        self.assertEqual(self._main(run=fake_run_with(self.pcap, writer=False)), 3)
        self.assertFalse(os.path.exists(self.state))

    def test_empty_capture_that_grows_fails(self):
        open(self.pcap, "wb").close()

        def grow():
            with open(self.pcap, "ab") as f:
                f.write(PCAPNG_MAGIC + b"packet")
        self.assertEqual(self._main(during=grow), 1)
        self.assertEqual(self.state_result(), "fail")

    def test_non_capture_bytes_exit_3(self):
        with open(self.pcap, "wb") as f:
            f.write(b"not a capture")
        self.assertEqual(self._main(), 3)
        self.assertFalse(os.path.exists(self.state))

    def test_no_live_tcpdump_exits_3(self):
        self.assertEqual(self._main(run=fake_run_with(self.pcap, writer=False)), 3)
        self.assertFalse(os.path.exists(self.state))

    def test_capture_not_covering_every_magnitude_pid_exits_3(self):
        run = fake_run_with(self.pcap, pids_in_filter=("100", "101", "102"))
        self.assertEqual(self._main(run=run), 3)
        self.assertFalse(os.path.exists(self.state))

    def test_no_magnitude_processes_exits_3(self):
        base = fake_run_with(self.pcap)

        def run(argv, timeout=60):
            if argv[0] == "ps":
                return done("  200     1 /usr/bin/unrelated\n")
            return base(argv, timeout)
        self.assertEqual(self._main(run=run), 3)

    def test_poll_errors_fail(self):
        self.assertEqual(self._main(polled=(0, [], 2)), 1)
        self.assertEqual(self.state_result(), "fail")

    def test_foreign_socket_fails(self):
        self.assertEqual(self._main(polled=(0, [("102", "magnitude", "a->54.225.198.112:443")], 0)), 1)

    def test_failed_llocal_runs_fail(self):
        self.assertEqual(self._main(polled=(1, [], 0)), 1)

    def test_at_rest_canary_is_reported_not_failed(self):
        orig = mec.uuid.uuid4

        class U:
            hex = "fixed"
        mec.uuid.uuid4 = lambda: U()
        with open(os.path.join(self.at_rest, "chats.sqlite"), "wb") as f:
            f.write(b"EGRESS-CANARY-fixed")
        try:
            self.assertEqual(self._main(), 0)
        finally:
            mec.uuid.uuid4 = orig
        with open(self.state) as f:
            self.assertEqual(json.load(f)["at_rest"], [os.path.join(self.at_rest, "chats.sqlite")])

    def test_download_active_writes_nothing(self):
        self.assertEqual(self._main(run=fake_run_with(self.pcap, models=DOWNLOADING_MODELS)), 3)
        self.assertFalse(os.path.exists(self.state))

    def test_magnitude_down_writes_nothing(self):
        self.assertEqual(self._main(run=fake_run_with(self.pcap, version=None)), 3)
        self.assertFalse(os.path.exists(self.state))


class PollingTest(unittest.TestCase):
    def test_polls_until_margin_after_exit(self):
        ticks = iter([0.0, 0.0, 10.0, 10.0])
        calls = []
        rc, hits, errors = mec.run_with_polling(
            [sys.executable, "-c", "pass"],
            lambda: [1],
            lambda pids: calls.append(1) or [("1", "m", "x->1.2.3.4:443")],
            interval=0.01, margin=1.0, clock=lambda: next(ticks), sleep=lambda s: None)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(len(hits), len(calls))
        self.assertEqual(errors, 0)

    def test_empty_pid_set_and_lsof_errors_count_as_errors(self):
        ticks = itertools.chain([0.0], itertools.repeat(10.0))
        pid_sets = itertools.chain([[]], itertools.repeat([1]))
        rc, hits, errors = mec.run_with_polling(
            [sys.executable, "-c", "pass"],
            lambda: next(pid_sets),
            lambda pids: None,
            interval=0.01, margin=1.0, clock=lambda: next(ticks), sleep=lambda s: None)
        self.assertEqual(hits, [])
        self.assertGreaterEqual(errors, 2)

if __name__ == "__main__":
    unittest.main()
