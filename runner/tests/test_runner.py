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
