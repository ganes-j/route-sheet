"""Tests for bin/codex-dispatch-run, the Lane B dispatch runner.

    /usr/bin/python3 -m unittest tests.test_codex_dispatch_run

A fake `codex` binary records its argv and writes a run-log banner, so no
network and no credits are needed. Worktree operations run against a real
temporary git repo.
"""
import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "codex-dispatch-run")

loader = importlib.machinery.SourceFileLoader("cdr", TOOL)
spec = importlib.util.spec_from_loader("cdr", loader)
cdr = importlib.util.module_from_spec(spec)
loader.exec_module(cdr)

# Assembled at runtime so the source holds no credential-shaped URL for leak-check to flag.
USERINFO = "u" + ":" + "p"

FAKE_CODEX = r'''#!/bin/sh
# records argv, prints a Codex-shaped banner, echoes stdin length, then edits a file if asked
printf '%s\n' "$@" > "$FAKE_CODEX_ARGS"
model="gpt-5.6-sol"; effort="medium"; wd="."
prev=""
for a in "$@"; do
  case "$prev" in
    -m) model="$a";;
    -C) wd="$a";;
    -c) case "$a" in model_reasoning_effort=*) effort="${a#model_reasoning_effort=}";; esac;;
  esac
  prev="$a"
done
cat >/dev/null
echo "OpenAI Codex v0.151.0"
echo "--------"
echo "workdir: $wd"
echo "model: $model"
echo "provider: openai"
echo "approval: never"
echo "sandbox: workspace-write [workdir, /tmp, \$TMPDIR]"
echo "reasoning effort: $effort"
echo "reasoning summaries: none"
echo "session id: 01a1-test-session"
echo "--------"
if [ -n "$FAKE_CODEX_EDIT" ]; then printf 'edited by fake codex\n' >> "$wd/$FAKE_CODEX_EDIT"; fi
if [ -n "$FAKE_CODEX_LINK" ]; then ln -s "$FAKE_CODEX_LINK_TARGET" "$wd/$FAKE_CODEX_LINK"; fi
if [ -n "$FAKE_CODEX_STAGE" ]; then git -C "$wd" add -A; fi
if [ -n "$FAKE_CODEX_SLEEP" ]; then sleep "$FAKE_CODEX_SLEEP"; fi
if [ -n "$FAKE_CODEX_CREDITS" ]; then echo "ERROR: Your workspace is out of credits. Ask your workspace owner to refill in order to continue."; fi
echo "done"
'''


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True, check=True).stdout


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        with open(os.path.join(self.home, ".claude", "CODEX_MODELS.md"), "w") as fh:
            fh.write("| Tier (model id) | Role |\n|---|---|\n| **Sol** (`gpt-5.6-sol`) | x |\n| **Luna** (`gpt-5.6-luna`) | y |\n")
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", ".")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        with open(os.path.join(self.repo, "app.py"), "w") as fh:
            fh.write("print('hi')\n")
        with open(os.path.join(self.repo, ".gitignore"), "w") as fh:
            fh.write(".worktrees/\n.env\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        self.codex = os.path.join(self.bin, "codex")
        with open(self.codex, "w") as fh:
            fh.write(FAKE_CODEX)
        os.chmod(self.codex, stat.S_IRWXU)
        self.args_file = os.path.join(self.tmp.name, "argv.txt")
        self.prompt = os.path.join(self.tmp.name, "prompt.md")
        with open(self.prompt, "w") as fh:
            fh.write("<task>say hi</task>\n")
        self.env = dict(os.environ, HOME=self.home, FAKE_CODEX_ARGS=self.args_file,
                        PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        self.env.pop("FAKE_CODEX_EDIT", None)
        for var in ("FAKE_CODEX_CREDITS", "FAKE_CODEX_LINK", "FAKE_CODEX_LINK_TARGET", "FAKE_CODEX_STAGE", "FAKE_CODEX_SLEEP"):
            self.env.pop(var, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args, env=None):
        r = subprocess.run(["/usr/bin/python3", TOOL] + list(args), capture_output=True, text=True,
                           env=env or self.env, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def prepare(self, *extra, env=None):
        code, out, err = self.run_tool("prepare", "U9", "--repo", self.repo, "--prompt", self.prompt, *extra, env=env)
        state = json.loads(out) if code == 0 else None
        return code, state, err

    def wait(self, state):
        for _ in range(100):
            if not cdr.process_alive(state["pid"]):
                return
            time.sleep(0.05)

    def argv(self):
        with open(self.args_file) as fh:
            return fh.read().split("\n")


class Prepare(Harness):
    def test_creates_worktree_launches_codex_and_writes_state(self):
        code, state, err = self.prepare()
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isdir(state["worktree"]))
        self.assertEqual(state["worktree"], os.path.join(self.repo, ".worktrees", "codex-U9"))
        self.assertIn("scratch", state)
        self.wait(state)
        argv = self.argv()
        self.assertEqual(argv[0], "exec")
        self.assertNotIn("-m", argv)
        self.assertIn("-C", argv)
        self.assertIn(state["worktree"], argv)
        self.assertIsNone(state["model_requested"])
        self.assertTrue(os.path.exists(os.path.join(state["scratch"], "run.log")))

    def test_model_and_effort_flags_are_passed_and_recorded(self):
        code, state, err = self.prepare("--model", "gpt-5.6-luna", "--effort", "low")
        self.assertEqual(code, 0, err)
        self.wait(state)
        argv = self.argv()
        self.assertIn("-m", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.6-luna")
        self.assertIn("model_reasoning_effort=low", argv)
        self.assertEqual(state["model_requested"], "gpt-5.6-luna")

    def test_uncatalogued_model_is_refused_unless_allowed(self):
        code, state, err = self.prepare("--model", "gpt-9-nope")
        self.assertEqual(code, 4)
        self.assertIn("not in CODEX_MODELS.md", err)
        self.assertFalse(os.path.isdir(os.path.join(self.repo, ".worktrees", "codex-U9")))
        code, state, err = self.prepare("--model", "gpt-9-nope", "--allow-uncatalogued")
        self.assertEqual(code, 0, err)
        self.wait(state)

    def test_kill_switch_refuses_before_any_worktree(self):
        open(os.path.join(self.home, ".claude", ".router-off"), "w").close()
        code, state, err = self.prepare()
        self.assertEqual(code, 2)
        self.assertFalse(os.path.isdir(os.path.join(self.repo, ".worktrees")))

    def test_unignored_worktrees_dir_refuses(self):
        with open(os.path.join(self.repo, ".gitignore"), "w") as fh:
            fh.write(".env\n")
        git(self.repo, "commit", "-q", "-am", "drop ignore")
        code, state, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertIn(".worktrees", err)

    def test_tracked_prod_credential_hard_skips(self):
        with open(os.path.join(self.repo, "settings.yaml"), "w") as fh:
            fh.write("db: postgres://%s@db-prod.example.com:5432/x\n" % USERINFO)
        git(self.repo, "add", "settings.yaml")
        git(self.repo, "commit", "-q", "-m", "cred")
        code, state, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertIn("db-prod.example.com", err)
        self.assertFalse(os.path.isdir(os.path.join(self.repo, ".worktrees", "codex-U9")))

    def test_uppercase_scheme_credential_hard_skips(self):
        with open(os.path.join(self.repo, "settings.yaml"), "w") as fh:
            fh.write("db: POSTGRES://%s@db-prod.example.com:5432/x\n" % USERINFO)
        git(self.repo, "add", "settings.yaml")
        git(self.repo, "commit", "-q", "-m", "cred")
        code, state, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertIn("db-prod.example.com", err)

    def test_gitignored_env_is_scrubbed_by_the_worktree(self):
        with open(os.path.join(self.repo, ".env"), "w") as fh:
            fh.write("DATABASE_URL=postgres://%s@db-prod.example.com/x\n" % USERINFO)
        code, state, err = self.prepare()
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(os.path.join(state["worktree"], ".env")))
        self.wait(state)

    def test_tracked_json_with_userinfo_is_caught(self):
        with open(os.path.join(self.repo, "local.json"), "w") as fh:
            fh.write('{"url": "postgresql://%s@db-proxy.example.net:5432/app"}\n' % USERINFO)
        git(self.repo, "add", "local.json")
        git(self.repo, "commit", "-q", "-m", "json cred")
        code, state, err = self.prepare()
        self.assertEqual(code, 3)
        self.assertIn("local.json", err)

    def test_second_prepare_for_same_unit_refuses_while_running(self):
        code, state, err = self.prepare()
        self.assertEqual(code, 0, err)
        self.wait(state)
        code2, _, err2 = self.prepare()
        self.assertEqual(code2, 3)
        self.assertIn("exists", err2)


class StatusAndCheck(Harness):
    def test_status_parses_banner_and_exit(self):
        code, state, _ = self.prepare("--model", "gpt-5.6-luna")
        self.wait(state)
        code, out, err = self.run_tool("status", "U9", "--repo", self.repo)
        self.assertEqual(code, 0, err)
        s = json.loads(out)
        self.assertEqual(s["model"], "gpt-5.6-luna")
        self.assertEqual(s["effort"], "medium")
        self.assertEqual(s["session_id"], "01a1-test-session")
        self.assertFalse(s["running"])
        self.assertFalse(s["out_of_credits"])

    def test_status_detects_out_of_credits(self):
        env = dict(self.env, FAKE_CODEX_CREDITS="1")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, _ = self.run_tool("status", "U9", "--repo", self.repo)
        self.assertTrue(json.loads(out)["out_of_credits"])

    def test_check_pass_prints_outcome_line_with_model(self):
        env = dict(self.env, FAKE_CODEX_EDIT="app.py")
        code, state, _ = self.prepare("--model", "gpt-5.6-luna", env=env)
        self.wait(state)
        code, out, err = self.run_tool("check", "U9", "--repo", self.repo, "--files", "app.py",
                                       "--verify", "grep -q 'edited by fake codex' app.py")
        self.assertEqual(code, 0, err)
        line = out.strip().splitlines()[-1]
        self.assertTrue(line.startswith("U9 · codex-implementer:gpt-5.6-luna · PASS · re-check "), line)
        self.assertIn("green", line)
        self.assertIn("01a1-test-session", line)
        self.assertIn(time.strftime("%Y-%m-%d"), line)
        self.assertTrue(os.path.exists(os.path.join(state["scratch"], "outcome.txt")))

    def test_check_fails_on_out_of_scope_file(self):
        env = dict(self.env, FAKE_CODEX_EDIT="rogue.txt")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, err = self.run_tool("check", "U9", "--repo", self.repo, "--files", "app.py", "--verify", "true")
        self.assertEqual(code, 1)
        self.assertIn("rogue.txt", out + err)
        self.assertIn("· FAIL ·", out)

    def test_check_no_wait_refuses_while_codex_is_running(self):
        env = dict(self.env, FAKE_CODEX_EDIT="app.py", FAKE_CODEX_SLEEP="5")
        code, state, _ = self.prepare(env=env)
        code, out, err = self.run_tool("check", "U9", "--repo", self.repo, "--files", "app.py",
                                       "--verify", "true", "--no-wait")
        self.assertEqual(code, 3)
        self.assertIn("still running", err)
        self.assertNotIn("PASS", out)
        os.killpg(os.getpgid(state["pid"]), 15)

    def test_check_fails_when_verify_is_red_or_diff_empty(self):
        code, state, _ = self.prepare()
        self.wait(state)
        code, out, _ = self.run_tool("check", "U9", "--repo", self.repo, "--files", "app.py", "--verify", "true")
        self.assertEqual(code, 1)
        self.assertIn("empty diff", out)
        env = dict(self.env, FAKE_CODEX_EDIT="app.py")
        self.run_tool("cleanup", "U9", "--repo", self.repo)
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, _ = self.run_tool("check", "U9", "--repo", self.repo, "--files", "app.py", "--verify", "false")
        self.assertEqual(code, 1)
        self.assertIn("red", out)


class ApplyAndCleanup(Harness):
    def test_apply_refuses_without_reviewed_then_applies(self):
        env = dict(self.env, FAKE_CODEX_EDIT="app.py")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo)
        self.assertEqual(code, 4)
        self.assertIn("--reviewed", err)
        with open(os.path.join(self.repo, "app.py")) as fh:
            self.assertNotIn("edited by fake codex", fh.read())
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.repo, "app.py")) as fh:
            self.assertIn("edited by fake codex", fh.read())
        self.assertIn("app.py", git(self.repo, "status", "--short"))

    def test_apply_copies_untracked_files(self):
        env = dict(self.env, FAKE_CODEX_EDIT="new_module.py")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed")
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "new_module.py")))

    def test_apply_includes_files_codex_staged(self):
        env = dict(self.env, FAKE_CODEX_EDIT="staged_module.py", FAKE_CODEX_STAGE="1")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.repo, "staged_module.py")) as fh:
            self.assertIn("edited by fake codex", fh.read())

    def test_apply_conflict_leaves_the_repo_untouched(self):
        env = dict(self.env, FAKE_CODEX_EDIT="new_module.py", FAKE_CODEX_STAGE="1")
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        with open(os.path.join(state["worktree"], "app.py"), "a") as fh:
            fh.write("tracked edit\n")
        with open(os.path.join(self.repo, "new_module.py"), "w") as fh:
            fh.write("mine\n")
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed")
        self.assertEqual(code, 1)
        self.assertIn("new_module.py", err)
        with open(os.path.join(self.repo, "app.py")) as fh:
            self.assertNotIn("tracked edit", fh.read())
        with open(os.path.join(self.repo, "new_module.py")) as fh:
            self.assertEqual(fh.read(), "mine\n")
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed", "--force")
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.repo, "app.py")) as fh:
            self.assertIn("tracked edit", fh.read())
        with open(os.path.join(self.repo, "new_module.py")) as fh:
            self.assertIn("edited by fake codex", fh.read())

    def test_untracked_symlink_is_applied_as_a_link(self):
        secret = os.path.join(self.tmp.name, "outside.txt")
        with open(secret, "w") as fh:
            fh.write("outside contents\n")
        env = dict(self.env, FAKE_CODEX_LINK="link.txt", FAKE_CODEX_LINK_TARGET=secret)
        code, state, _ = self.prepare(env=env)
        self.wait(state)
        code, out, err = self.run_tool("apply", "U9", "--repo", self.repo, "--reviewed")
        self.assertEqual(code, 0, err)
        dst = os.path.join(self.repo, "link.txt")
        self.assertTrue(os.path.islink(dst))
        self.assertEqual(os.readlink(dst), secret)

    def test_cleanup_removes_worktree_and_state(self):
        code, state, _ = self.prepare()
        self.wait(state)
        code, out, err = self.run_tool("cleanup", "U9", "--repo", self.repo)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.isdir(state["worktree"]))
        self.assertNotIn("codex-U9", git(self.repo, "worktree", "list"))


if __name__ == "__main__":
    unittest.main()


class ManifestModel(Harness):
    def test_model_comes_from_the_manifest_row(self):
        manifest = os.path.join(self.tmp.name, "plan-routing.md")
        with open(manifest, "w") as fh:
            fh.write("## Assignments\n- U9 → codex-implementer:gpt-5.6-luna (worktree-scrub) [full] — reason — load-bearing check: `true`\n")
        code, state, err = self.prepare("--manifest", manifest)
        self.assertEqual(code, 0, err)
        self.wait(state)
        argv = self.argv()
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.6-luna")
        self.assertEqual(state["model_requested"], "gpt-5.6-luna")

    def test_explicit_model_overrides_manifest(self):
        manifest = os.path.join(self.tmp.name, "plan-routing.md")
        with open(manifest, "w") as fh:
            fh.write("- U9 → codex-implementer:gpt-5.6-luna [full]\n")
        code, state, err = self.prepare("--manifest", manifest, "--model", "gpt-5.6-sol")
        self.assertEqual(code, 0, err)
        self.wait(state)
        self.assertEqual(state["model_requested"], "gpt-5.6-sol")

    def test_plain_row_inherits_config(self):
        manifest = os.path.join(self.tmp.name, "plan-routing.md")
        with open(manifest, "w") as fh:
            fh.write("- U9 → codex-implementer (worktree-scrub) [full]\n")
        code, state, err = self.prepare("--manifest", manifest)
        self.assertEqual(code, 0, err)
        self.wait(state)
        self.assertNotIn("-m", self.argv())
