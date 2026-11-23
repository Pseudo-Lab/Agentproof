"""Deterministic tests: no real API requests or API keys."""
import copy
from collections import Counter
import csv
import io
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
import unittest
from unittest.mock import patch

import benchmark as b
import run
from summarize import summarize


class FakeResponse:
    def __init__(self, value):
        self.value = json.dumps(value).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return self.value


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        (b.ROOT / "runs").mkdir(exist_ok=True)
        self.temp = b.ROOT / "runs" / ("test_" + uuid.uuid4().hex)
        self.temp.mkdir()
        self.env = patch.dict(os.environ, {"PLAN_RUN_DIR": str(self.temp), "PLAN_MOCK": "1"})
        self.env.start()
        self.cfg = b.settings()
    def tearDown(self):
        self.env.stop()
        assert self.temp.resolve().is_relative_to((b.ROOT / "runs").resolve())
        shutil.rmtree(self.temp)

    def test_cost_includes_cached_writes_and_all_output_tokens(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["models"]["low"].update(input_per_million=2, cached_input_per_million=0.5,
                                      cache_write_per_million=2.5, output_per_million=8)
        payload = {"model": "test-model", "usage": {"prompt_tokens": 1000, "completion_tokens": 500,
                   "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
                   "completion_tokens_details": {"reasoning_tokens": 300}},
                   "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
        ledger = b.Ledger("B", "test", 0)
        with patch.dict(os.environ, {"PLAN_MOCK": "0", "OPENAI_API_KEY": "test-only"}), \
                patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            self.assertEqual(b.model_call(cfg, "low", [], "single", ledger), "ok")
        # 700 ordinary + 200 read + 100 write + 500 output (reasoning not double-counted)
        self.assertAlmostEqual(ledger.data["calls"][0]["cost_usd"], 0.00575)

    def test_truncated_output_preserves_spend(self):
        payload = {"usage": {"prompt_tokens": 100, "completion_tokens": 50},
                   "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}
        ledger = b.Ledger("B", "test", 0)
        with patch.dict(os.environ, {"PLAN_MOCK": "0", "OPENAI_API_KEY": "test-only"}), \
                patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            with self.assertRaises(ValueError):
                b.model_call(self.cfg, "low", [], "single", ledger)
        self.assertGreater(ledger.data["calls"][0]["cost_usd"], 0)
        self.assertEqual(ledger.data["calls"][0]["status"], "error")

    def test_missing_usage_is_unknown_cost_not_free(self):
        ledger = b.Ledger("B", "test", 0)
        with patch.dict(os.environ, {"PLAN_MOCK": "0", "OPENAI_API_KEY": "test-only"}), \
                patch("urllib.request.urlopen", return_value=FakeResponse({"usage": {}})):
            with self.assertRaises(ValueError):
                b.model_call(self.cfg, "low", [], "single", ledger)
        self.assertIsNone(ledger.data["calls"][0]["cost_usd"])

    def test_dependencies_reject_cycles_and_duplicate_ids(self):
        plan = b.mock_plan()
        plan["steps"][0]["depends_on"] = ["S1"]
        with self.assertRaises(ValueError):
            b.validate_plan(json.dumps(plan), self.cfg)
        plan = b.mock_plan()
        plan["steps"].append(copy.deepcopy(plan["steps"][0]))
        with self.assertRaises(ValueError):
            b.validate_plan(json.dumps(plan), self.cfg)

    def test_c_uses_low_for_candidates_and_synthesis(self):
        response = b.generate("C", "test task", "test")
        rec = json.loads(Path(response["metadata"]["record_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(rec["calls"]), self.cfg["experiment"]["workers"] + 1)
        self.assertTrue(all(c["role"] == "low" for c in rec["calls"]))
        self.assertEqual(response["tokenUsage"]["numRequests"], 4)

    def test_judge_does_not_see_group_or_worker_drafts(self):
        response = b.generate("C", "test task", "test")
        original = b.model_call
        def capture(cfg, role, messages, stage, ledger):
            self.assertEqual(role, "judge")
            data = json.loads(messages[-1]["content"])
            self.assertEqual(set(data), {"task", "reference", "plan"})
            return original(cfg, role, messages, stage, ledger)
        with patch.object(b, "model_call", side_effect=capture):
            result = b.grade(response["output"], {"task": "test task", "eval_reference": "private",
                                                 "task_layer": "coupled_sources"},
                             response["metadata"])
        self.assertEqual(result["score"], 0.75)

    def test_invalid_plan_is_zero_without_paid_judge(self):
        response = b.generate("B", "test task", "test")
        result = b.grade("invalid", {"task": "test", "eval_reference": "test"}, response["metadata"])
        self.assertEqual(result["score"], 0)
        rec = json.loads(Path(response["metadata"]["record_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(rec["calls"]), 1)
        self.assertEqual(rec["status"], "invalid_plan")

    def test_judge_failure_is_not_a_zero_quality_plan(self):
        response = b.generate("B", "test task", "test")
        with patch.object(b, "model_call", return_value='{"scores": {}}'):
            with self.assertRaises(RuntimeError):
                b.grade(response["output"], {"task": "test", "eval_reference": "test"}, response["metadata"])
        rec = json.loads(Path(response["metadata"]["record_path"]).read_text(encoding="utf-8"))
        self.assertEqual(rec["status"], "judge_error")
        self.assertNotIn("score_100", rec)

    def test_high_score_with_critical_error_fails(self):
        response = b.generate("B", "test task", "test")
        verdict = {"scores": {k: 4 for k in b.AXES},
                   "reasons": {k: "evidence" for k in b.AXES},
                   "critical_errors": [{"description": "Impossible budget", "step_id": "S1"}]}
        with patch.object(b, "model_call", return_value=json.dumps(verdict)):
            result = b.grade(response["output"], {"task": "test", "eval_reference": "test"}, response["metadata"])
        self.assertEqual(result["score"], 1)
        self.assertFalse(result["pass"])

    def test_partial_failure_retains_completed_parallel_call_cost(self):
        def fake(cfg, role, messages, stage, ledger):
            ledger.add({"stage": stage, "role": role, "cost_usd": 0.01, "status": "ok"})
            if stage == "candidate_2":
                raise RuntimeError("worker failed")
            return json.dumps(b.mock_plan())
        with patch.object(b, "model_call", side_effect=fake):
            response = b.generate("C", "test", "test")
        self.assertIn("error", response)
        self.assertAlmostEqual(response["cost"], 0.03)
        self.assertEqual(response["tokenUsage"]["numRequests"], 3)

    def test_summary_reports_missing_and_unknown_cost(self):
        ledger = b.Ledger("A", "test", 0)
        ledger.add({"stage": "single", "cost_usd": None})
        ledger.finish(status="generation_error")
        b.write_json(self.temp / "manifest.json", {"settings": self.cfg, "mock": True})
        b.write_json(self.temp / "invocation.json", {"expected_samples": 3, "repeat": 1})
        summary = summarize(self.temp)
        self.assertEqual(summary["missing_samples"], 2)
        self.assertEqual(summary["groups"]["A"]["unknown_cost_calls"], 1)
        self.assertIsNone(summary["groups"]["A"]["mean_score_100"])
        self.assertIn("unclassified", summary["layers"])

    def run_mock(self, *extra):
        argv = ["run.py", "--mock", "--engine", "python", "--repeat", "1",
                "--cases", str(b.ROOT / "cases.json"), "--config", str(b.ROOT / "experiment.toml"), *extra]
        with patch.object(run, "ROOT", self.temp), patch.object(sys, "argv", argv), \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(run.main(), 0)
        directory = Path(os.environ["PLAN_RUN_DIR"])
        return directory, json.loads((directory / "summary.json").read_text(encoding="utf-8"))

    def test_dataset_has_baseline_and_three_new_layers(self):
        cases = json.loads((b.ROOT / "cases.json").read_text(encoding="utf-8"))
        self.assertEqual(Counter(c["vars"]["task_layer"] for c in cases),
                         {"baseline": 6, "short_constraints": 2, "independent_sources": 2, "coupled_sources": 2})
        self.assertEqual(len({c["vars"]["task_id"] for c in cases}), len(cases))
        for case in cases:
            for key in ("task_id", "task", "eval_reference"):
                self.assertTrue(case["vars"][key].strip())
            if case["vars"]["task_layer"].endswith("_sources"):
                self.assertIn("[", case["vars"]["task"])

    def test_full_dataset_mock_reports_each_layer(self):
        directory, summary = self.run_mock()
        self.assertEqual(summary["recorded_samples"], 36)
        self.assertEqual(summary["missing_samples"], 0)
        self.assertEqual(summary["experiment_cost_usd"], 0)
        for layer, count in [("baseline", 6), ("short_constraints", 2),
                             ("independent_sources", 2), ("coupled_sources", 2)]:
            data = summary["layers"][layer]
            self.assertEqual(data["task_count"], count)
            self.assertEqual(data["recorded_samples"], count * 3)
            self.assertEqual(data["missing_samples"], 0)
            for group in "ABC":
                self.assertEqual(data["groups"][group]["scored"], count)
            self.assertEqual(data["comparisons"]["C-A"]["complete_paired_tasks"], count)
            self.assertIsNone(data["comparisons"]["C-A"]["quality_noninferiority_signal"])
        with (directory / "samples.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 36)
        self.assertEqual({r["task_layer"] for r in rows}, set(summary["layers"]))
        report = (directory / "summary.md").read_text(encoding="utf-8")
        self.assertIn("## Task layers", report)
        self.assertIn("| coupled_sources | C | 2 / 2 |", report)

    def test_layer_selection_precedes_limit(self):
        directory, summary = self.run_mock("--layer", "independent_sources", "--layer", "coupled_sources",
                                           "--limit", "3")
        self.assertEqual(summary["expected_samples"], 9)
        self.assertEqual(set(summary["layers"]), {"independent_sources", "coupled_sources"})
        cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
        self.assertEqual([c["vars"]["task_layer"] for c in cases],
                         ["independent_sources", "independent_sources", "coupled_sources"])

    def test_unknown_layer_is_rejected(self):
        with patch("sys.stderr", new_callable=io.StringIO) as error:
            with self.assertRaises(SystemExit) as caught:
                self.run_mock("--layer", "typo")
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("Unknown task layers: typo", error.getvalue())

    def test_legacy_cases_without_layer_are_supported(self):
        cases_path = self.temp / "legacy-cases.json"
        b.write_json(cases_path, [{"vars": {"task_id": "legacy", "task": "test", "eval_reference": "test"}}])
        _, summary = self.run_mock("--cases", str(cases_path), "--layer", "unclassified")
        self.assertEqual(summary["layers"]["unclassified"]["task_count"], 1)
        self.assertEqual(summary["missing_samples"], 0)

    def test_invalid_layer_metadata_is_rejected(self):
        cases_path = self.temp / "invalid-cases.json"
        b.write_json(cases_path, [{"vars": {"task_id": "invalid", "task": "test", "eval_reference": "test",
                                          "task_layer": None}}])
        with patch("sys.stderr", new_callable=io.StringIO) as error:
            with self.assertRaises(SystemExit) as caught:
                self.run_mock("--cases", str(cases_path))
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("Invalid case variable: task_layer", error.getvalue())

    def test_layer_summary_retains_errors_and_missing_pairs(self):
        cases = [{"vars": {"task_id": "good", "task_layer": "independent_sources"}},
                 {"vars": {"task_id": "failed", "task_layer": "coupled_sources"}}]
        b.write_json(self.temp / "cases.json", cases)
        b.write_json(self.temp / "manifest.json", {"settings": self.cfg, "mock": True})
        b.write_json(self.temp / "invocation.json", {"expected_samples": 6, "repeat": 1})
        for group in "ABC":
            response = b.generate(group, "test", "good")
            b.grade(response["output"], {"task": "test", "eval_reference": "test"}, response["metadata"])
        ledger = b.Ledger("A", "failed", 0)
        ledger.add({"stage": "single", "cost_usd": None})
        ledger.finish(status="generation_error")
        summary = summarize(self.temp)
        failed = summary["layers"]["coupled_sources"]
        self.assertEqual(failed["missing_samples"], 2)
        self.assertEqual(failed["groups"]["A"]["generation_errors"], 1)
        self.assertEqual(failed["groups"]["A"]["unknown_cost_calls"], 1)
        self.assertIsNone(failed["groups"]["A"]["mean_score_100"])
        self.assertEqual(failed["comparisons"]["C-A"]["complete_paired_tasks"], 0)


if __name__ == "__main__":
    unittest.main()
