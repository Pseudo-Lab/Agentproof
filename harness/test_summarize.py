"""Offline checks for submission integrity and the copy/run workflow."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from summarize import summarize

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'experiments/E00-offline-example/results/pilot/example-001'


class SubmissionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.manifest = json.loads((EXAMPLE / 'manifest.json').read_text())
        self.rows = [json.loads(line) for line in (EXAMPLE / 'trials.jsonl').read_text().splitlines()]

    def save(self):
        (self.path / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.path / 'trials.jsonl').write_text('\n'.join(json.dumps(row) for row in self.rows) + '\n')

    def test_example_summary_and_unmeasured_cost(self):
        self.save()
        result = summarize(self.path)
        self.assertEqual(result, json.loads((EXAMPLE / 'summary.json').read_text()))
        baseline = result['conditions']['baseline']
        self.assertEqual(baseline['successes'], 5)
        self.assertIsNone(baseline['metrics']['cost_usd']['total'])
        self.assertEqual(baseline['metrics']['cost_usd']['measured_trials'], 0)

    def test_missing_and_duplicate_trials_rejected(self):
        original = copy.deepcopy(self.rows)
        for rows in (original[:-1], original + [original[0]]):
            with self.subTest(size=len(rows)):
                self.rows = rows
                self.save()
                with self.assertRaises(ValueError):
                    summarize(self.path)

    def test_error_and_timeout_stay_in_denominator(self):
        for status in ('error', 'timeout'):
            with self.subTest(status=status):
                self.rows[0]['status'] = status
                self.rows[0]['score'] = None
                self.rows[0]['missing_reasons']['score'] = 'execution did not produce a score'
                self.save()
                baseline = summarize(self.path)['conditions']['baseline']
                self.assertEqual(baseline['trials'], 15)
                self.assertEqual(baseline['successes'], 4)
                self.assertEqual(baseline['all_repeats_success_tasks'], 0)

    def test_null_requires_reason_and_missing_field_rejected(self):
        del self.rows[0]['missing_reasons']['cost_usd']
        self.save()
        with self.assertRaisesRegex(ValueError, 'requires a missing reason'):
            summarize(self.path)
        del self.rows[0]['cost_usd']
        self.save()
        with self.assertRaisesRegex(ValueError, 'missing trial field'):
            summarize(self.path)

    def test_copy_run_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='E99-smoke-', dir=ROOT / 'experiments') as name:
            experiment = Path(name)
            shutil.copytree(ROOT / 'templates/experiment', experiment, dirs_exist_ok=True)
            command = [sys.executable, str(experiment / 'src/run.py'), '--run-id', 'smoke-001']
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            run_dir = experiment / 'results/pilot/smoke-001'
            before = (run_dir / 'trials.jsonl').read_bytes()
            self.assertEqual(summarize(run_dir)['conditions']['intervention']['successes'], 10)
            repeat = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertIn('already exists', repeat.stderr)
            self.assertEqual(before, (run_dir / 'trials.jsonl').read_bytes())


if __name__ == '__main__':
    unittest.main()
