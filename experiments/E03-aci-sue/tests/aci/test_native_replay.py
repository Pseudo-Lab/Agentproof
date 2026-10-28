"""Real mini batch CLI, Docker tools, deadline cancellation and native resume."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml
from minisweagent.config import get_config_from_spec
from minisweagent.utils.serialize import recursive_merge

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "aci-lens-smoke:mini-20261025"


@unittest.skipUnless(os.environ.get("ACI_NATIVE_REPLAY"), "Set ACI_NATIVE_REPLAY=1 for Docker integration")
class NativeReplayTests(unittest.TestCase):
    def fixture(self, commands, *, condition="baseline", seconds=30, calls=0, count=1, model=None, workers=1):
        temporary = tempfile.TemporaryDirectory(prefix="aci-mini-replay-")
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        repo = work / "repo"
        repo.mkdir()
        (repo / "mathops.py").write_text('# 합계\ndef add(a, b):\n    """éé"""\n    return a - b\n\nSENTINEL = 7\n')
        (repo / "answer.py").write_text("answer = 0\n")
        (repo / "test_mathops.py").write_text("from mathops import add, SENTINEL\ndef test_add():\n    assert add(2, 3) == 5\n    assert SENTINEL == 7\n")
        (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        for arguments in (["init", "-q"], ["add", "."], ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"]):
            subprocess.run(["git", "-C", str(repo), *arguments], check=True)
        cfg = recursive_merge(*(get_config_from_spec(str(path)) for path in (
            "swebench.yaml", ROOT / "src/minisweagent/config/extra/aci-common.yaml", ROOT / f"src/minisweagent/config/extra/aci-{condition}.yaml",
            ROOT / "src/minisweagent/config/extra/aci-tool-first.yaml",
            ROOT / "src/minisweagent/config/extra/aci-wall600.yaml")))
        cfg["agent"].update(wall_time_limit_seconds=seconds, step_limit=calls)
        cfg["environment"]["run_args"] += ["--mount", f"type=bind,src={repo},target=/fixture,readonly"]
        cfg["run"]["env_startup_command"] = "cp -r /fixture/. /testbed/\n" + cfg["run"]["env_startup_command"]
        if model is None:
            outputs = []
            for i, command in enumerate(commands):
                actions = command if isinstance(command, list) else [{"command": command}]
                tool_calls = []
                for j, action in enumerate(actions):
                    action["tool_call_id"] = f"call_{i}_{j}"
                    tool_calls.append({"id": action["tool_call_id"], "type": "function", "function": {
                        "name": "bash", "arguments": json.dumps({"command": action["command"]})}})
                outputs.append({"role": "assistant", "content": "Fixture action", "tool_calls": tool_calls,
                                "extra": {"actions": actions, "cost": 0}})
            model = {"model_class": "minisweagent.models.test_models.DeterministicToolcallModel",
                     "model_name": "fixture", "cost_per_call": 0, "outputs": outputs}
        cfg["model"] = recursive_merge(cfg["model"], model)
        path = work / "replay.yaml"
        path.write_text(yaml.safe_dump(cfg))
        dataset = work / "dataset"
        dataset.mkdir()
        (dataset / "test.jsonl").write_text("\n".join(json.dumps({"instance_id": f"fixture-{i}",
            "problem_statement": "Fix addition.", "base_commit": "HEAD", "image_name": IMAGE}) for i in range(count)))
        output = work / "results"
        command = [sys.executable, "-m", "minisweagent.run.benchmarks.aci", "--subset", str(dataset), "--split", "test",
                   "-c", str(path), "--workers", str(workers), "-o", str(output)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((output / "fixture-0/fixture-0.traj.json").exists(), result.stdout + result.stderr)
        traces = [json.loads((output / f"fixture-{i}/fixture-{i}.traj.json").read_text()) for i in range(count)]
        predictions = json.loads((output / "preds.json").read_text())
        self.assertEqual(len(predictions), count)
        for i, trace in enumerate(traces):
            self.assertEqual(predictions[f"fixture-{i}"]["model_patch"], trace["info"]["submission"])
        return traces, command, output, result.stdout + result.stderr

    def test_sue_heredocs_index_refresh_submission_and_resume(self):
        commands = [
            'test -n "$(find /root/aci-tools/search/.cache -name output.pkl -print -quit)" && echo INDEX_PREPARED',
            "cat <<'EOF' > /tmp/aci-body.txt\n\tTAB_PRESERVED\nSOUNIQUEEOF\nEOF\npython -c \"from pathlib import Path; assert Path('/tmp/aci-body.txt').read_text() == '\\tTAB_PRESERVED\\nSOUNIQUEEOF\\n'; print('HEREDOC_OK')\"",
            "search_method add",
            "readCode mathops.py --selector add",
            "editCode mathops.py replace_node add --replacement " + shlex.quote("def add(a, b):\n    return a + b"),
            "search_method add",
            "python -m pytest -q test_mathops.py",
            "create_file /tmp/aci-tool-test/new.txt before && str_replace /tmp/aci-tool-test/new.txt before after && cat /tmp/aci-tool-test/new.txt",
            "git diff -- mathops.py > patch.txt",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt",
        ]
        traces, command, output, log = self.fixture(commands, condition="sue")
        trace = traces[0]
        self.assertEqual(trace["info"]["exit_status"], "Submitted", log)
        self.assertEqual(trace["info"]["model_stats"]["api_calls"], len(commands))
        self.assertIn("+    return a + b", trace["info"]["submission"])
        self.assertEqual(trace["info"]["submission"].count("diff --git"), 1)
        results = [message["content"] for message in trace["messages"] if message["role"] == "tool"]
        self.assertIn("INDEX_PREPARED", results[0])
        self.assertIn("HEREDOC_OK", results[1])
        self.assertIn("return a - b", results[2])
        self.assertIn("<file>mathops.py</file>", results[2])
        self.assertIn("def add(a, b):", results[3])
        self.assertIn("return a - b", results[3])
        self.assertNotIn("SENTINEL", results[3])
        self.assertIn("return a + b", results[5])
        self.assertIn("1 passed", results[6])
        self.assertIn("after", results[7])
        self.assertIn("first call readCode", trace['messages'][0]['content'])
        self.assertNotIn("agentless_skeleton", trace['messages'][0]['content'])
        saved = (output / "fixture-0/fixture-0.traj.json").read_bytes()
        resumed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45)
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        self.assertIn("Skipping 1 existing instances", resumed.stdout + resumed.stderr)
        self.assertEqual(saved, (output / "fixture-0/fixture-0.traj.json").read_bytes())

    def test_agentless_u_variant_installs_and_describes_only_selected_reader(self):
        traces, _, _, log = self.fixture([
            'test -z "$(command -v readCode)" && test -z "$(command -v editCode)" && agentless_skeleton mathops.py',
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git diff",
        ], condition='u-agentless')
        trace = traces[0]
        self.assertEqual(trace['info']['exit_status'], 'Submitted', log)
        prompt = trace['messages'][0]['content']
        self.assertIn('first call agentless_skeleton', prompt)
        self.assertNotIn('readCode', prompt)
        result = next(message['content'] for message in trace['messages'] if message['role'] == 'tool')
        self.assertIn('def add(a, b):', result)
        self.assertIn('...', result)
        self.assertNotIn('return a - b', result)

    def test_deadline_kills_command_children_skips_pending_actions_and_continues_batch(self):
        actions = [{"command": "printf 'answer = 42\\n' > answer.py; (sleep 8; printf 'answer = 99\\n' > answer.py) & wait"},
                   {"command": "printf 'answer = 99\\n' > answer.py"}]
        traces, _, _, log = self.fixture([actions], seconds=2, count=2, workers=2)
        for trace in traces:
            self.assertEqual(trace["info"]["exit_status"], "TimeExceeded", log)
            self.assertIn("+answer = 42", trace["info"]["submission"])
            self.assertNotIn("+answer = 99", trace["info"]["submission"])
            self.assertTrue(trace["messages"][-1]["extra"]["autosubmitted"])
            self.assertEqual(trace["info"]["model_stats"]["api_calls"], 1)

    def test_call_limit_recovers_new_files_and_excludes_patch_artifact(self):
        traces, _, _, log = self.fixture([
            "printf 'answer = 42\\n' > answer.py; printf 'created = 1\\n' > created.py; printf 'artifact\\n' > patch.txt",
            "printf 'answer = 99\\n' > answer.py"], calls=1)
        trace = traces[0]
        self.assertEqual(trace["info"]["exit_status"], "LimitsExceeded", log)
        self.assertEqual(trace["info"]["model_stats"]["api_calls"], 1)
        self.assertIn("+answer = 42", trace["info"]["submission"])
        self.assertIn("+created = 1", trace["info"]["submission"])
        self.assertNotIn("patch.txt", trace["info"]["submission"])
        self.assertNotIn("+answer = 99", trace["info"]["submission"])

    def test_completed_agent_releases_container_even_while_references_remain(self):
        from minisweagent.run.benchmarks.aci import BudgetAgent
        from minisweagent.environments.docker import DockerEnvironment
        from minisweagent.models.test_models import DeterministicModel, make_output
        from minisweagent.run.benchmarks.utils.batch_progress import RunBatchProgressManager

        env = DockerEnvironment(image=IMAGE, cwd="/tmp", interpreter=["bash", "-c"], run_args=["--rm", "--network", "none"])
        self.addCleanup(env.cleanup)
        progress = RunBatchProgressManager(1)
        progress.on_instance_start("cleanup")
        model = DeterministicModel(cost_per_call=0, outputs=[make_output("Submit", [{
            "command": "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\npatch\\n'"}], cost=0)])
        agent = BudgetAgent(model, env, progress_manager=progress, instance_id="cleanup",
                            system_template="Test.", instance_template="{{task}}", cost_limit=0,
                            step_limit=1, wall_time_limit_seconds=5)
        self.assertEqual(agent.run("Finish.")["exit_status"], "Submitted")
        deadline = time.monotonic() + 15
        while subprocess.run(["docker", "inspect", env.container_id], capture_output=True).returncode == 0:
            self.assertLess(time.monotonic(), deadline, "Completed agent left its container running")
            time.sleep(0.2)
        # Saving native results must still work after explicit environment cleanup.
        self.assertIs(agent.env, env)
        self.assertEqual(agent.serialize()["info"]["submission"], "patch\n")

    def test_command_child_is_dead_before_patch_recovery_while_container_stays_alive(self):
        from minisweagent.environments.docker import DockerEnvironment
        from minisweagent.exceptions import TimeExceeded
        from minisweagent.run.benchmarks.aci import DeadlineEnvironment

        env = DockerEnvironment(image=IMAGE, cwd="/tmp", interpreter=["bash", "-c"], run_args=["--rm", "--network", "none"])
        self.addCleanup(env.cleanup)
        bounded = DeadlineEnvironment(env, time.monotonic() + 1)
        with self.assertRaises(TimeExceeded):
            bounded.execute({"command": "printf before > deadline-probe; (sleep 3; printf after > deadline-probe) & wait"})
        # Keep the container running past the child's scheduled write, so that
        # container cleanup cannot accidentally make this test pass.
        result = env.execute({"command": "sleep 3; cat deadline-probe"})
        self.assertEqual(result["output"], "before")

    def test_deadline_cancels_real_http_without_retry_and_continues_batch(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(time.monotonic())
                # Repeated successes exercise callback logging before a stalled request.
                previous = sum(message['role'] == 'tool' for message in payload['messages'])
                if previous >= 4:
                    time.sleep(8)
                body = json.dumps({"id": "fixture", "object": "chat.completion", "created": 0,
                    "model": "fixture", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                        "role": "assistant", "content": "Fixture action", "tool_calls": [{"id": "call_fixture", "type": "function",
                        "function": {"name": "bash", "arguments": json.dumps({"command": "printf 'answer = 42\\n' > answer.py"})}}]}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        start = time.monotonic()
        # Two concurrent instances time out; a queued third instance must still run.
        traces, _, _, log = self.fixture([], seconds=5, count=3, workers=2, model={
            "model_class": "minisweagent.run.benchmarks.aci.DeadlineModel", "model_name": "openai/fixture", "cost_tracking": "ignore_errors",
            "model_kwargs": {"api_base": f"http://127.0.0.1:{server.server_port}/v1", "api_key": "EMPTY"}})
        self.assertEqual(len(requests), 15, log)
        self.assertLess(time.monotonic() - start, 24, log)
        self.assertNotIn("Retrying", log)
        self.assertNotIn("LoggingWorker: event loop changed", log)
        for trace in traces:
            self.assertEqual(trace["info"]["exit_status"], "TimeExceeded", log)
            self.assertIn("+answer = 42", trace["info"]["submission"])
            self.assertEqual(trace["info"]["model_stats"]["api_calls"], 5)
            responses = [message["extra"]["response"] for message in trace["messages"]
                         if "response" in message.get("extra", {})]
            self.assertEqual(len(responses), 4)
            self.assertEqual(sum(response["usage"]["total_tokens"] for response in responses), 80)
