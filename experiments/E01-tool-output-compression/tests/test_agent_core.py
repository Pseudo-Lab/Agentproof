"""agent_core 단위 테스트. 모델·네트워크 호출 없음.
실행(레포 루트): .venv/bin/python -m unittest discover -s experiments/E01-tool-output-compression/tests
mini-swe-agent 가 없어도 이 파일의 테스트는 돈다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import agent_core as ac  # noqa: E402


def obs(i):
    # mini-swe-agent 텍스트 모드가 만드는 관찰 메시지와 같은 꼴
    content = f"<returncode>0</returncode>\n<output>\noutput-{i}-" + "x" * 50 + "\n</output>"
    return {"role": "user", "content": content, "extra": {"raw_output": f"output-{i}", "returncode": 0, "timestamp": 0.0}}


def msgs(n_tools):
    out = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "TASK: fix it"}]
    for i in range(n_tools):
        out.append({"role": "assistant", "content": f"```mswea_bash_command\ncmd{i}\n```",
                    "extra": {"actions": [{"command": f"cmd{i}"}], "cost": 0.0}})
        out.append(obs(i))
    return out


class CompressionTests(unittest.TestCase):
    def test_five_or_fewer_tool_outputs_unchanged(self):
        for n in (0, 1, 5):
            m = msgs(n)
            out, stats = ac.compress_old_observations(m, keep_last=5)
            self.assertEqual([x["content"] for x in out], [x["content"] for x in m])
            self.assertEqual(stats["compressed_messages"], 0)

    def test_sixth_compresses_only_oldest(self):
        m = msgs(6)
        out, stats = ac.compress_old_observations(m, keep_last=5)
        tool_idx = [i for i, x in enumerate(m) if ac.is_tool_output(x)]
        first = out[tool_idx[0]]
        self.assertEqual(first["content"], f"(출력 {len(m[tool_idx[0]]['content'])}자 생략됨)")
        self.assertTrue(first["extra"]["compressed"])
        for i in tool_idx[1:]:
            self.assertEqual(out[i]["content"], m[i]["content"])
        self.assertEqual(stats["compressed_messages"], 1)
        self.assertEqual(stats["removed_chars"], len(m[tool_idx[0]]["content"]))

    def test_non_tool_messages_never_touched(self):
        m = msgs(12)
        out, _ = ac.compress_old_observations(m, keep_last=5)
        for a, b in zip(m, out):
            if not ac.is_tool_output(a):
                self.assertIs(a, b)

    def test_original_list_not_mutated(self):
        m = msgs(8)
        snapshot = json.dumps(m, sort_keys=True)
        ac.compress_old_observations(m, keep_last=5)
        self.assertEqual(snapshot, json.dumps(m, sort_keys=True))

    def test_role_name_is_not_the_criterion(self):
        # 과제 문장은 user 역할이지만 도구 출력이 아니므로 keep_last=0 이어도 남아야 한다
        m = msgs(3)
        out, _ = ac.compress_old_observations(m, keep_last=0)
        self.assertEqual(out[1]["content"], "TASK: fix it")
        self.assertEqual(sum(x["content"].startswith("(출력") for x in out), 3)

    def test_format_error_user_message_is_not_tool_output(self):
        m = msgs(2) + [{"role": "user", "content": "Format error", "extra": {"interrupt_type": "FormatError"}}]
        self.assertFalse(ac.is_tool_output(m[-1]))


TASK = {
    "task_id": "T-demo",
    "issue": "add should add",
    "repo": {"file": "solution.py", "content": "def add(a, b):\n    return a - b\n"},
    "hidden_test": {"imports": "", "setup": "", "entry_point": "add",
                    "test": "def check(f):\n    assert f(1, 2) == 3\n    assert f(0, 0) == 0\n"},
}


class GraderTests(unittest.TestCase):
    def _grade_with(self, content):
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            ac.build_task_workdir(TASK, wd)
            (wd / "solution.py").write_text(content)
            return ac.grade(TASK, wd)

    def test_correct_passes(self):
        self.assertEqual(self._grade_with("def add(a, b):\n    return a + b\n")["status"], "success")

    def test_wrong_fails(self):
        self.assertEqual(self._grade_with("def add(a, b):\n    return a - b\n")["status"], "failure")

    def test_syntax_error_is_failure_not_error(self):
        self.assertEqual(self._grade_with("def add(a, b)\n    return\n")["status"], "failure")

    def test_agent_cannot_tamper_hidden_test(self):
        r = self._grade_with("def add(a, b):\n    return a - b\ndef check(f):\n    pass\n")
        self.assertEqual(r["status"], "failure")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ac.grade(TASK, Path(d))["status"], "failure")

    def test_workdir_has_no_hidden_test(self):
        with tempfile.TemporaryDirectory() as d:
            ac.build_task_workdir(TASK, Path(d))
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["ISSUE.md", "solution.py"])


class RougeTests(unittest.TestCase):
    def test_identical_and_disjoint(self):
        self.assertAlmostEqual(ac.rouge_l_f1("a b c", "a b c"), 1.0)
        self.assertEqual(ac.rouge_l_f1("a b", "c d"), 0.0)


if __name__ == "__main__":
    unittest.main()
