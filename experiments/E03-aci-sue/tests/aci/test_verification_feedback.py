"""V' feedback contracts: outer pytest results and visible baseline failure identities."""
import os
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import test_related_tests as fixtures

related_tests = fixtures.related_tests


def summary(rows, totals):
    return "================ short test summary info ================\n" + rows + "\n" + (
        f"================ {totals} in 0.01s ================\n" if totals else "")


CHILD = ("E   ImportError: intentional child error\nERROR collecting child.py\n" +
         summary("ERROR child.py - ImportError: intentional child error", "1 error"))


class SummaryTests(unittest.TestCase):
    def test_captured_child_errors_are_not_outer_outcomes(self):
        for rc, row, total, state, error in (
            (0, "PASSED tests/test_outer.py::test_capture", "1 passed", "passed", None),
            (1, "FAILED tests/test_outer.py::test_capture - AssertionError: outer", "1 failed", "failed",
             "AssertionError: outer"),
            (1, "ERROR tests/test_outer.py::test_capture - RuntimeError: setup", "1 error", "failed",
             "RuntimeError: setup"),
            (2, "ERROR tests/test_outer.py - ImportError: actual collection", "1 error", "unavailable",
             "ImportError: actual collection"),
        ):
            with self.subTest(state=state, row=row):
                record = related_tests.outcome(CHILD + summary(row, total), rc)
                self.assertEqual(record["outcome"], state)
                self.assertEqual(record["first_error"], error)
                self.assertNotIn("child.py", record["status"])

    def test_partial_counts_exit_and_timeout_remain_unverified(self):
        row = "PASSED tests/test_outer.py::test_capture"
        for log, rc, timeout in (
            (CHILD + summary(row, None), 0, False),
            (summary(row, "2 passed"), 0, False),
            (summary(row, "1 passed, 1 failed"), 0, False),
            (summary(row, "1 passed"), 1, False),
            (summary(row, "1 passed"), None, True),
        ):
            with self.subTest(log=log, rc=rc, timeout=timeout):
                record = related_tests.outcome(log, rc, timeout)
                self.assertEqual(record["outcome"], "timeout" if timeout else "unavailable")

    def test_teardown_error_is_not_overwritten_by_passing_body(self):
        node = "tests/test_outer.py::test_capture"
        rows = [f"PASSED {node}", f"ERROR {node} - RuntimeError: teardown"]
        for order in (rows, rows[::-1]):
            record = related_tests.outcome(summary("\n".join(order), "1 passed, 1 error"), 1)
            self.assertEqual(record["outcome"], "failed")
            self.assertEqual(record["status"], {node: "error"})

    def test_parameterized_ids_keep_spaces_and_internal_hyphens(self):
        node = "tests/test_outer.py::test_capture[a - b [nested]]"
        record = related_tests.outcome(summary(f"FAILED {node} - AssertionError: outer", "1 failed"), 1)
        self.assertEqual(record["status"], {node: "failed"})
        self.assertEqual(record["reason"], {node: "AssertionError: outer"})

    def test_older_pytest_seconds_and_truncated_reason(self):
        passed = summary("PASSED tests/test_outer.py::test_capture", "1 passed").replace("0.01s", "0.01 seconds")
        self.assertEqual(related_tests.outcome(CHILD + passed, 0)["outcome"], "passed")
        failed = ("________________ test_outer ________________\n"
                  "E   Failed: DID NOT WARN with expected warning\n"
                  "---------------- Captured stdout call ----------------\n" + CHILD +
                  summary("FAILED tests/test_outer.py::test_outer - Fai...", "1 failed"))
        record = related_tests.outcome(failed, 1)
        self.assertEqual(record["first_error"], "Failed: DID NOT WARN with expected warning")

    def test_real_pytest_captures_child_collection_error(self):
        with tempfile.TemporaryDirectory(prefix="aci-nested-pytest-") as tmp:
            root = Path(tmp)
            (root / "child.py").write_text("import deliberately_missing_aci_dependency\n")
            for success in (True, False):
                with self.subTest(outer_success=success):
                    (root / "test_outer.py").write_text(
                        "import subprocess, sys\n"
                        "def test_capture():\n"
                        "    child = subprocess.run([sys.executable, '-m', 'pytest', '-rA', 'child.py'], "
                        "stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)\n"
                        "    print(child.stdout)\n"
                        "    assert child.returncode == 2\n"
                        f"    assert {success!r}, 'outer assertion'\n")
                    run = subprocess.run([sys.executable, "-m", "pytest", "-rA", "-p", "no:cacheprovider",
                                          "test_outer.py"], cwd=tmp, capture_output=True, text=True, timeout=30,
                                         env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                                                  PYTHONDONTWRITEBYTECODE="1"))
                    self.assertIn("ERROR collecting child.py", run.stdout)
                    record = related_tests.outcome(run.stdout, run.returncode)
                    self.assertEqual(record["outcome"], "passed" if success else "failed")
                    self.assertEqual(record["status"], {"test_outer.py::test_capture": "passed" if success else "failed"})
                    self.assertNotIn("deliberately_missing", str(record["first_error"]))


class UnittestSummaryTests(unittest.TestCase):
    def test_interleaved_stdout_does_not_lose_explicit_test_status(self):
        log = ('test_first (sample.Tests) ... setup message\nok\n'
               'test_second (sample.Tests)\nA docstring. ... another message\nFAIL\n'
               'test_third (sample.Tests) ... ok\n')
        self.assertEqual(related_tests.parse(log)[0], {
            'sample.Tests.test_first': 'passed', 'sample.Tests.test_second': 'failed',
            'sample.Tests.test_third': 'passed'})
        incomplete = 'test_pending (sample.Tests) ... setup message\n'
        self.assertEqual(related_tests.parse(incomplete)[0], {})
        self.assertEqual(related_tests.parse(incomplete + 'test_next (sample.Tests) ... ok\nok\n')[0],
                         {'sample.Tests.test_next': 'passed'})

    @staticmethod
    def subtest_log(kind='ERROR', count=1, ending='FAILED (errors=1)'):
        return ('test_values (sample.Tests) ... test_ok (sample.Tests) ... ok\n' +
                ''.join('=' * 70 + '\n' + kind + ': test_values (sample.Tests) (value=' + repr(i) + ')\n' +
                        '-' * 70 + '\nTraceback (most recent call last):\n'
                        'ValueError: broken value\n\n' for i in range(count)) +
                '-' * 70 + '\nRan 2 tests in 0.01s\n\n' + ending + '\n')

    def test_subtests_aggregate_to_parent_and_compare_with_base(self):
        current = related_tests.outcome(self.subtest_log(count=2, ending='FAILED (errors=2)'), 1)
        baseline = related_tests.outcome('test_values (sample.Tests) ... ok\ntest_ok (sample.Tests) ... ok\n'
                                         'Ran 2 tests in 0.01s\n\nOK\n', 0)
        self.assertEqual(current['outcome'], 'failed')
        self.assertEqual(current['status']['sample.Tests.test_values'], 'error')
        self.assertEqual(sum(v == 'error' for v in current['status'].values()), 1)
        rendered = '\n'.join(related_tests.render(fixtures.ExecutionStatusTests.result(current, baseline), 1500))
        self.assertIn('1 new', rendered)
        self.assertIn('sample.Tests.test_values', rendered)
        self.assertIn('ValueError', rendered)

    def test_parent_failures_override_success_but_partial_or_child_reports_do_not(self):
        log = self.subtest_log(kind='FAIL', ending='FAILED (failures=1)')
        self.assertEqual(related_tests.unittest_failures('test_values (sample.Tests) ... ok\n'+log),
                         {'sample.Tests.test_values': 'failed'})
        self.assertEqual(related_tests.unittest_failures(self.subtest_log(count=1, ending='FAILED (errors=2)')), {})
        self.assertEqual(related_tests.unittest_failures(log.rsplit('Ran 2 tests', 1)[0]), {})
        outer = 'test_outer (outer.Tests) ... ok\nRan 1 test in 0.02s\n\nOK\n'
        self.assertEqual(related_tests.unittest_failures(log+outer), {})
        failed_outer = self.subtest_log().replace('sample.Tests', 'outer.Tests')
        self.assertEqual(related_tests.unittest_failures(log+failed_outer), {'outer.Tests.test_values': 'error'})

    def test_real_unittest_subtests_keep_failure_and_error_on_one_parent(self):
        class Probe(unittest.TestCase):
            def test_values(self):
                for value in (1, 2):
                    with self.subTest(value=value):
                        if value == 1:
                            self.assertEqual(value, 0)
                        else:
                            raise ValueError('broken value')
        Probe.__qualname__ = 'Probe'  # The repository runner discovers module-level test classes.
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Probe))
        record = related_tests.outcome(stream.getvalue(), 0 if result.wasSuccessful() else 1)
        self.assertEqual(record['outcome'], 'failed')
        self.assertEqual(list(record['status'].values()), ['error'])


class FailureRenderingTests(unittest.TestCase):
    def test_aborted_current_and_passing_base_report_command_failure_without_zero_regressions(self):
        current = related_tests.outcome('Traceback (most recent call last):\nRuntimeError: broken import\n', 1)
        baseline = related_tests.outcome(summary('PASSED tests/test_x.py::test_x', '1 passed'), 0)
        result = fixtures.ExecutionStatusTests.result(current, baseline)
        result['selection'] = dict(method='base_execution_index', full_suite_fallback=False,
                                   indexed_full_native_suite=False, execution_unit='native_test_id',
                                   unchecked_reasons=['untraced dependencies ' * 30])
        for limit in (1500, 10000):
            rendered = '\n'.join(related_tests.render(result, limit)) + '\n'
            self.assertLessEqual(len(rendered), limit)
            self.assertIn('command failed on edited code; same command passed on base', rendered)
            self.assertIn('test-level comparison incomplete', rendered)
            self.assertIn('RuntimeError: broken import', rendered)
            self.assertIn('[log]', rendered)
            self.assertNotIn('0 new', rendered)
            self.assertNotIn('0 failed', rendered)
        self.assertEqual(current['outcome'], 'unavailable')
        self.assertEqual(current['status'], {})  # Do not invent a failed test ID.

    def test_unconfirmed_command_failures_and_stale_results_do_not_claim_base_comparison(self):
        aborted = related_tests.outcome('Traceback (most recent call last):\nRuntimeError: broken import\n', 1)
        passed = related_tests.outcome(summary('PASSED tests/test_x.py::test_x', '1 passed'), 0)
        for current, baseline in ((aborted, aborted), (related_tests.outcome('', None), passed),
                                  (related_tests.outcome('', None, timed_out=True), passed),
                                  (related_tests.outcome('', 0), passed)):
            rendered = '\n'.join(related_tests.render(fixtures.ExecutionStatusTests.result(current, baseline), 1500))
            self.assertNotIn('same command passed on base', rendered)
            self.assertIn('test-level comparison incomplete', rendered)
        result = fixtures.ExecutionStatusTests.result(aborted, passed)
        result['freshness'] = 'stale'
        self.assertNotIn('[comparison]', '\n'.join(related_tests.render(result, 1500)))

    def test_categories_and_omission_counts_under_both_caps(self):
        for limit in (1500, 10000):
            with self.subTest(limit=limit):
                names = [f"tests/test_x.py::test_{i:02d}" for i in range(24)]
                current = related_tests.outcome(summary("\n".join(f"FAILED {n} - AssertionError: bad" for n in names),
                                                        "24 failed"), 1)
                baseline = related_tests.outcome(summary("\n".join(
                    f"{'PASSED' if i < 8 else 'FAILED'} {n}" for i, n in enumerate(names[:16])),
                    "8 passed, 8 failed"), 1)
                rendered = "\n".join(related_tests.render(fixtures.ExecutionStatusTests.result(current, baseline), limit)) + "\n"
                self.assertLessEqual(len(rendered), limit)
                for label in ("(new)", "(baseline unverified)", "(also failing before edits)"):
                    self.assertIn(label, rendered)
                shown = sum(line.startswith("  failed") for line in rendered.splitlines())
                self.assertLessEqual(shown, 8)
                self.assertIn(f"{24 - shown} identities omitted", rendered)
                self.assertIn("[base=failed, current=failed]", rendered)
                self.assertTrue(rendered.endswith("[tests] end; the output of this command follows\n"))


class NativeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='aci-unit-diagnostic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'checks.py').write_text(
            'import os, pytest, app\n'
            '@pytest.mark.parametrize("value", app.values, ids=lambda v: "pid-%s-%s" % (os.getpid(), v))\n'
            'def test_value(value):\n    assert app.calculate(value) == value + 1\n')

    def execute(self, source):
        import json
        (self.root / 'app.py').write_text(source)
        path = self.root / 'units.json'
        run = subprocess.run(
            [sys.executable, str(fixtures.BUNDLE / 'aci_test_units.py'), str(path),
             '-rA', '-p', 'no:cacheprovider', 'checks.py'], cwd=self.root,
            env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1'),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        result = related_tests.outcome(run.stdout, run.returncode)
        result['test_units'] = json.loads(path.read_text())
        return result

    def render(self, current, baseline):
        result = fixtures.ExecutionStatusTests.result(current, baseline)
        result['selection'] = dict(execution_unit='native_pytest_unit',
                                   units=list(current['test_units']['units']))
        return result, '\n'.join(related_tests.render(result, 1500)) + '\n'

    def test_changed_failure_inside_existing_unit_with_unstable_ids_and_order(self):
        import aci_test_units as units
        source = 'values = [0, 1]\ndef calculate(value):\n    return 0 if value == 0 else value + 1\n'
        baseline = self.execute(source)
        for body, values in [('0', '[0, 1]'), ('value + 1 if value == 0 else 0', '[0, 1]'),
                             ('value + 1 if value == 0 else 0', '[1, 0]')]:
            with self.subTest(body=body, values=values):
                current = self.execute(f'values = {values}\ndef calculate(value):\n    return {body}\n')
                after, before = current['test_units'], baseline['test_units']
                self.assertTrue(set(after['case_reports']).isdisjoint(before['case_reports']))
                selector = 'checks.py::test_value'
                self.assertEqual(units.comparison(after, before, [selector])['existing'], [selector])
                detail = units.failure_detail(after, before, [selector])
                self.assertEqual(detail['kind'], 'unpaired_summaries')
                self.assertTrue(any('(1 + 1)' in message for phase, message in detail['current']))
                result, rendered = self.render(current, baseline)
                self.assertIn('unpaired failures', rendered)
                self.assertIn('(1 + 1)', rendered)
                self.assertIn('base=[1x call: assert 0 == (0 + 1)]', rendered)
                self.assertIn('0 new, 1 also failing', rendered)
                self.assertLessEqual(len(rendered), 1500)
                result['freshness'] = 'stale'
                self.assertNotIn('unpaired failures', '\n'.join(related_tests.render(result, 1500)))
        unchanged = self.execute(source)
        detail = units.failure_detail(unchanged['test_units'], baseline['test_units'], ['checks.py::test_value'])
        self.assertEqual(detail['kind'], 'unpaired_summaries')
        _, rendered = self.render(unchanged, baseline)
        self.assertNotIn('current-only', rendered)
        self.assertIn('base=[1x call: assert 0 == (0 + 1)]; current=[1x call: assert 0 == (0 + 1)]', rendered)

    def test_new_unit_diagnostic_replaces_unrelated_first_error(self):
        (self.root / 'checks.py').write_text(
            'import app\ndef test_a_existing():\n    assert False, "existing failure"\n'
            'def test_z_new():\n    assert app.enabled, "changed behavior"\n')
        baseline = self.execute('enabled = True\n')
        current = self.execute('enabled = False\n')
        self.assertIn('existing failure', current['first_error'])
        _, rendered = self.render(current, baseline)
        self.assertIn('failed (new) [base=passed, current=failed]: checks.py::test_z_new', rendered)
        self.assertIn('changed behavior', rendered)
        self.assertNotIn('[first error]', rendered)
        self.assertIn('1 new, 1 also failing', rendered)
        self.assertLessEqual(len(rendered), 1500)

    def test_missing_diagnostics_or_partial_units_do_not_prove_text_absence(self):
        import copy
        import aci_test_units as units
        baseline = self.execute('values = [0, 1]\ndef calculate(value):\n    return 0 if value == 0 else value + 1\n')
        current = self.execute('values = [0, 1]\ndef calculate(value):\n    return 0\n')
        selector = 'checks.py::test_value'
        legacy = copy.deepcopy(baseline['test_units'])
        for case in legacy['case_reports'].values():
            for report in case['reports']:
                report.pop('message', None)
        self.assertIsNone(units.failure_detail(current['test_units'], legacy, [selector]))
        for status in ('partial', 'incomplete', 'skipped'):
            incomplete = copy.deepcopy(baseline['test_units'])
            incomplete['units'][selector]['outcome'] = status
            self.assertIsNone(units.failure_detail(current['test_units'], incomplete, [selector]))






if __name__ == "__main__":
    unittest.main()
