import importlib.util
import os
import pathlib
import subprocess
import tempfile
import unittest

RUNNER_PATH = pathlib.Path(__file__).resolve().parents[1] / "runner.py"


def load_runner(env=None):
    for key in list(os.environ):
        if key.startswith("RUNNER_") or key in ("WORKSPACE_DIR", "OPENCODE_MODEL", "OPENROUTER_API_KEY"):
            os.environ.pop(key, None)
    if env:
        os.environ.update(env)
    spec = importlib.util.spec_from_file_location("runner_under_test", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpencodeAgentTest(unittest.TestCase):
    def test_stub_agent_command_is_executed_in_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = os.path.join(tmp, "stub.sh")
            with open(stub, "w") as handle:
                handle.write("#!/usr/bin/env bash\nmkdir -p out && echo hi > out/x.txt\n")
            os.chmod(stub, 0o755)
            runner = load_runner({"RUNNER_AGENT_CMD": stub, "RUNNER_TOKEN": "t"})
            code, output = runner.run_agent("ignored", cwd=tmp)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "out", "x.txt")))

    def test_agent_cmd_env_read_at_call_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = os.path.join(tmp, "stub.sh")
            with open(stub, "w") as handle:
                handle.write("#!/usr/bin/env bash\nmkdir -p out && echo hi > out/x.txt\n")
            os.chmod(stub, 0o755)
            runner = load_runner({"RUNNER_TOKEN": "t"})
            os.environ["RUNNER_AGENT_CMD"] = stub
            try:
                code, output = runner.run_agent("ignored", cwd=tmp)
            finally:
                os.environ.pop("RUNNER_AGENT_CMD", None)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "out", "x.txt")))


class ImplementViaAgentTest(unittest.TestCase):
    def _seed_repo(self, tmp):
        remote = os.path.join(tmp, "remote.git")
        subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
        work = os.path.join(tmp, "demo")
        subprocess.run(["git", "init", "-q", "-b", "main", work], check=True)
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            subprocess.run(["git", "-C", work, "config", key, value], check=True)
        with open(os.path.join(work, "README.md"), "w") as handle:
            handle.write("seed\n")
        subprocess.run(["git", "-C", work, "add", "."], check=True)
        subprocess.run(["git", "-C", work, "commit", "-qm", "seed"], check=True)
        subprocess.run(["git", "-C", work, "remote", "add", "origin", remote], check=True)
        subprocess.run(["git", "-C", work, "push", "-q", "-u", "origin", "main"], check=True)
        return work

    def test_implement_runs_agent_and_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self._seed_repo(tmp)
            stub = os.path.join(tmp, "stub.sh")
            with open(stub, "w") as handle:
                handle.write("#!/usr/bin/env bash\nmkdir -p src && echo new > src/a.txt\n")
            os.chmod(stub, 0o755)
            runner = load_runner({
                "RUNNER_TOKEN": "t",
                "RUNNER_AGENT_MODE": "opencode",
                "RUNNER_AGENT_CMD": stub,
                "RUNNER_SKIP_PUSH": "1",
                "RUNNER_GATE": "0",
                "WORKSPACE_DIR": tmp,
            })
            result = runner.implement({
                "card": {"id": 7, "type": "feature", "title": "Add a.txt", "description": "create file"},
                "repository": {"slug": "demo", "github_url": work, "default_branch": "main"},
                "llm": {},
            })
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["branch"], "feature/card-7")
            branch = subprocess.run(["git", "-C", work, "rev-parse", "--abbrev-ref", "HEAD"],
                                    capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "feature/card-7")


class AgentEnvAndModelTest(unittest.TestCase):
    def test_opencode_provider_is_preserved_and_key_exported(self):
        runner = load_runner({"RUNNER_TOKEN": "t"})
        env, model = runner.agent_env_and_model(
            {"api_key": "k", "model": "opencode/deepseek-v4.1-flash"})
        self.assertEqual(model, "opencode/deepseek-v4.1-flash")
        self.assertEqual(env["OPENCODE_API_KEY"], "k")
        self.assertNotIn("openrouter/opencode/deepseek-v4.1-flash", model)

    def test_bare_model_gets_openrouter_prefix_and_key(self):
        runner = load_runner({"RUNNER_TOKEN": "t"})
        env, model = runner.agent_env_and_model(
            {"api_key": "k", "model": "deepseek-v4.1-flash"})
        self.assertEqual(model, "openrouter/deepseek-v4.1-flash")
        self.assertEqual(env["OPENROUTER_API_KEY"], "k")

    def test_provider_prefixed_non_opencode_model_uses_openrouter_key(self):
        runner = load_runner({"RUNNER_TOKEN": "t"})
        env, model = runner.agent_env_and_model(
            {"api_key": "k", "model": "some/model"})
        self.assertEqual(model, "some/model")
        self.assertEqual(env["OPENROUTER_API_KEY"], "k")


class ReviewViaAgentTest(unittest.TestCase):
    def _runner(self, tmp, agent_body):
        stub = os.path.join(tmp, "review_stub.sh")
        with open(stub, "w") as handle:
            handle.write("#!/usr/bin/env bash\n" + agent_body + "\n")
        os.chmod(stub, 0o755)
        return load_runner({
            "RUNNER_TOKEN": "t",
            "RUNNER_AGENT_MODE": "opencode",
            "RUNNER_AGENT_CMD": stub,
            "WORKSPACE_DIR": tmp,
        })

    def test_review_block_returns_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self._runner(tmp, "echo 'BLOCK: missing tests'")
            result = runner.review({
                "card": {"id": 1, "title": "x"},
                "repository": {"slug": "demo", "default_branch": "main"},
                "llm": {},
            })
            self.assertFalse(result["ok"])
            self.assertIn("BLOCK:", result["summary"])

    def test_review_ok_returns_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self._runner(tmp, "echo 'OK: looks good'")
            result = runner.review({
                "card": {"id": 1, "title": "x"},
                "repository": {"slug": "demo", "default_branch": "main"},
                "llm": {},
            })
            self.assertTrue(result["ok"])
            self.assertIn("OK:", result["summary"])


class GateTest(unittest.TestCase):
    def test_detects_php_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "composer.json"), "w").write("{}")
            runner = load_runner({"RUNNER_TOKEN": "t"})
            commands = runner.detect_gate_commands(tmp)
            self.assertTrue(any("pint" in " ".join(c) for c in commands))

    def test_gate_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = load_runner({"RUNNER_TOKEN": "t", "RUNNER_GATE_CMD": "bash -c 'exit 1'"})
            ok, output = runner.run_gate(tmp)
            self.assertFalse(ok)
            self.assertIn("gate", output.lower())

    def test_gate_reports_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = load_runner({"RUNNER_TOKEN": "t", "RUNNER_GATE_CMD": "bash -c 'exit 0'"})
            ok, output = runner.run_gate(tmp)
            self.assertTrue(ok)

    def test_resolve_prefers_repo_local_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = os.path.join(tmp, "vendor", "bin", "pint")
            os.makedirs(os.path.dirname(local), exist_ok=True)
            with open(local, "w") as handle:
                handle.write("#!/usr/bin/env bash\nexit 0\n")
            os.chmod(local, 0o755)
            runner = load_runner({"RUNNER_TOKEN": "t"})
            resolved = runner.resolve_gate_command(tmp, ["vendor/bin/pint", "--test"])
            self.assertEqual(resolved[0], local)

    def test_resolve_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = load_runner({"RUNNER_TOKEN": "t"})
            self.assertIsNone(runner.resolve_gate_command(tmp, ["definitely-not-a-real-binary-xyz"]))

    def test_gate_skipped_when_no_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = load_runner({"RUNNER_TOKEN": "t"})
            ok, output = runner.run_gate(tmp)
            self.assertTrue(ok)
            self.assertIn("skipped", output.lower())
