"""API 없이 공통 평가 환경 ↔ 알고리즘 작업 프로세스 통신을 확인한다.

    python3 -m unittest discover -s tests      (src/ 에서)

알고리즘 venv 대신 현재 인터프리터로 example 어댑터를 띄운다.
"""

import dataclasses
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from harness.registry import algorithms  # noqa: E402
from harness.worker import AdapterError, AdapterProcess  # noqa: E402

SESSION = {"session_id": "s1", "date": "1:56 pm on 8 May, 2023", "date_iso": "2023-05-08",
           "turns": [{"speaker": "Alice", "role": "user", "text": "I live in Seoul.", "turn_id": "D1:1"},
                     {"speaker": "Bob", "role": "assistant", "text": "I adopted a dog.", "turn_id": "D1:2"}]}


class AdapterIPCTest(unittest.TestCase):
    def setUp(self):
        spec = dataclasses.replace(algorithms()["example"], venv=Path(sys.executable).parents[1])
        self.proc = AdapterProcess(spec)

    def tearDown(self):
        self.proc.close()

    def test_round_trip(self):
        info, _ = self.proc.call("setup", config={})
        self.assertEqual(info["name"], "example")
        self.proc.call("reset", scope="conv-1", speakers=["Alice", "Bob"])
        self.proc.call("ingest", scope="conv-1", session=SESSION)
        result, seconds = self.proc.call("retrieve", scope="conv-1", question="Where does Alice live?",
                                         reference_date=None, top_k=1)
        self.assertEqual(result["items"][0]["text"], "Alice: I live in Seoul.")
        self.assertEqual(result["items"][0]["source_turn_ids"], ["D1:1"])
        self.assertGreaterEqual(seconds, 0)

    def test_adapter_error_is_reported_and_process_survives(self):
        self.proc.call("setup", config={})
        with self.assertRaises(AdapterError):   # example 은 native answer 를 구현하지 않는다
            self.proc.call("answer", scope="x", question="q", reference_date=None, retrieval={"items": []})
        self.proc.call("reset", scope="conv-2", speakers=["A", "B"])   # 오류 뒤에도 같은 프로세스가 응답


if __name__ == "__main__":
    unittest.main()
