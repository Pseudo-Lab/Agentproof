"""Condition V' (tools/slcat/edit-diff/related_tests.py): existing tests for edited modules run in the background
and their outcome comes before a later command's output.

Host checks use a temporary pytest repository and a copy of the bundle with its own venv, like
test_edit_diff. ACI_G_DOCKER=1 adds SWE-bench container checks (Django runner, real startup command).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "tools/slcat/edit-diff"
EXTRA = ROOT / "configs"
sys.path.insert(0, str(BUNDLE))
import related_tests  # noqa: E402

TESTS_ENV = {k: str(v) for k, v in yaml.safe_load((EXTRA / "aci-common.yaml").read_text())["environment"]["env"].items()
             if k.startswith("ACI_TESTS_")}
MOD = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    return -a\n"
TEST_MOD = "from pkg.mod import add, neg\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\ndef test_neg():\n    assert neg(2) == -2\n"
TEST_OLD = "def test_already_broken():\n    assert False, 'broken at base'\n"


class NativeCommandTests(unittest.TestCase):
    def test_explicit_native_cache_setting_preserves_other_runner_arguments(self):
        from contextlib import chdir
        import impact_tests

        with tempfile.TemporaryDirectory() as tmp, chdir(tmp):
            Path('bin').mkdir()
            Path('bin/test').touch()
            Path('sympy').mkdir()
            for setting in (None, 'no', 'yes'):
                for seeded in ('0', '1'):
                    with self.subTest(cache=setting, seeded=seeded), patch.dict(os.environ, clear=True):
                        os.environ.update(ACI_TESTS_PAIRED_CONTEXT=seeded, ACI_TESTS_SEED='42',
                                          PATH=str(Path(sys.executable).parent))
                        if setting is not None:
                            os.environ['SYMPY_USE_CACHE'] = setting
                        command = related_tests.command(['sympy/checks.py'])
                        self.assertEqual(command[:2], ['python', 'bin/test'])
                        self.assertEqual(command[-1], 'sympy/checks.py')
                        self.assertEqual('-C' in command, setting != 'yes')
                        self.assertEqual('--seed' in command, seeded == '1')
                        identity = impact_tests.environment()['env']
                        self.assertIn('SYMPY_USE_CACHE', identity)
                        self.assertEqual(identity['SYMPY_USE_CACHE'], setting)


class RelatedTestsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aci-vtests-")
        tmp = Path(self.tmp.name)
        self.bundle = tmp / "edit-diff"
        shutil.copytree(BUNDLE, self.bundle, ignore=shutil.ignore_patterns("__pycache__"))
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(self.bundle / ".venv")], check=True)
        (tmp / "bin").mkdir()
        (tmp / "bin" / "python").write_text(f"#!/bin/sh\nexec {sys.executable} \"$@\"\n")  # the test interpreter
        (tmp / "bin" / "python").chmod(0o755)
        (tmp / "next.sh").write_text("")
        self.repo = tmp / "repo"
        for path, text in {"pkg/__init__.py": "", "pkg/mod.py": MOD, "pkg/other.py": "X = 1\n",
                           "tests/test_mod.py": TEST_MOD, "tests/test_other.py": "def test_x():\n    assert True\n",
                           "tests/test_mod_old.py": "import pkg.mod\n\n\n" + TEST_OLD}.items():
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "base"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True)
        shutil.rmtree(related_tests.BASE, ignore_errors=True)

    def tearDown(self):
        subprocess.run(["pkill", "-f", str(self.bundle / "related_tests.py")])
        shutil.rmtree(related_tests.BASE, ignore_errors=True)
        self.tmp.cleanup()

    def sh(self, command, hook=True, diff=True, extra_env=None):
        tmp = Path(self.tmp.name)
        env = {"PATH": f"{tmp / 'bin'}:/usr/bin:/bin", "HOME": str(tmp), "ACI_G_PATH": str(ROOT / "tools/slcat/search-grep")}
        if hook:
            env |= {"BASH_ENV": str(self.bundle / "hook.sh"), "ACI_NEXT_BASH_ENV": str(tmp / "next.sh"),
                    "ACI_EDIT_TESTS": "1", **TESTS_ENV} | ({} if diff else {"ACI_EDIT_DIFF": "0"})
        env.update(extra_env or {})
        result = subprocess.run(["bash", "-c", command], cwd=self.repo, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=120)
        return result.stdout

    def wait_result(self):
        result = self.repo / ".git/aci-tests/result.json"
        for _ in range(300):
            if result.is_file():
                return json.loads(result.read_text())
            time.sleep(0.1)
        self.fail("no test result")

    def test_select_prefers_importing_and_same_name_tests(self):
        here = os.getcwd()
        os.chdir(self.repo)
        try:
            self.assertEqual(related_tests.select(["pkg/mod.py"], 3), ["tests/test_mod.py", "tests/test_mod_old.py"])
            self.assertEqual(related_tests.module_of("pkg/mod.py"), (".", "pkg.mod"))
            self.assertEqual(related_tests.select(["pkg/other.py"], 3), ["tests/test_other.py"])
        finally:
            os.chdir(here)

    def test_new_failure_reported_with_a_later_command(self):
        out = self.sh("sed -i 's/a + b/a - b/' pkg/mod.py")
        self.assertIn("[edit] pkg/mod.py: +1 -1 lines", out)
        self.assertIn("[tests] started in the background: python -m pytest -rA -p no:cacheprovider "
                      "tests/test_mod.py tests/test_mod_old.py", out)
        self.wait_result()
        out = self.sh("echo next")
        self.assertIn("[tests] background run: status=failed; exit=1; 1 passed, 2 failed", out)
        self.assertIn("1 new, 1 also failing before your edits, 0 failures unverified", out)
        self.assertIn("failed (new) [base=passed, current=failed]: tests/test_mod.py::test_add: assert -1 == 3", out)
        self.assertIn("test_already_broken", out)
        self.assertTrue(out.rstrip("\n").endswith("next"), out)
        self.assertEqual(self.sh("echo again"), "again\n")                          # shown once

    def test_old_failures_include_identity_and_both_states(self):
        self.sh("sed -i 's/return -a/return -1 * a/' pkg/mod.py", diff=False)
        result = self.wait_result()
        self.assertEqual(result["before"].get("tests/test_mod_old.py::test_already_broken"), "failed")
        out = self.sh("true")
        self.assertIn("status=failed; exit=1; 2 passed, 1 failed", out)
        self.assertIn("0 new, 1 also failing before your edits, 0 failures unverified", out)
        self.assertIn("same first error reproduced before edits", out)
        self.assertIn("failed (also failing before edits) [base=failed, current=failed]: "
                      "tests/test_mod_old.py::test_already_broken", out)
        self.assertNotIn("failed (new)", out)
        self.assertIn("[tests] end; the output of this command follows", out)

    def test_collection_failure_runs_baseline_and_is_not_a_failed_test(self):
        self.sh("printf 'def broken(:\\n' > pkg/mod.py", diff=False)
        result = self.wait_result()
        self.assertEqual(result["outcome"], "unavailable")
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["baseline"]["outcome"], "failed")  # the pre-existing assertion
        self.assertIn("SyntaxError", result["first_error"])
        self.assertIn("SyntaxError", Path(result["log_path"]).read_text())
        rendered = self.sh("true")
        self.assertIn("status=unavailable", rendered)
        self.assertIn("0 passed, 0 failed", rendered)

    def test_passed_tests_are_compared_to_base_without_claiming_bug_reproduction(self):
        self.sh("echo '# no executable change' >> pkg/other.py", diff=False)
        result = self.wait_result()
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["baseline"]["outcome"], "passed")
        self.assertIn("no failing-before/passing-after test demonstrated", self.sh("true"))

    def test_fail_to_pass_requires_observed_base_failure(self):
        (self.repo / "tests/test_other.py").write_text("from pkg.other import X\ndef test_x():\n    assert X == 2\n")
        subprocess.run(["git", "add", "tests/test_other.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "failing base test"],
                       cwd=self.repo, check=True)
        self.sh("sed -i 's/X = 1/X = 2/' pkg/other.py", diff=False)
        result = self.wait_result()
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["baseline"]["outcome"], "failed")
        self.assertIn("1 fail-to-pass tests", self.sh("true"))

    def test_diff_hidden_with_tests_only(self):
        out = self.sh("sed -i 's/a + b/b + a/' pkg/mod.py", diff=False)
        self.assertNotIn("[edit]", out)
        self.assertIn("[tests] started in the background", out)
        self.wait_result()  # Don't remove the temporary repository while its test process writes bytecode.

    def test_submit_and_recovery_outputs_unchanged(self):
        self.sh("sed -i 's/a + b/a - b/' pkg/mod.py")
        self.wait_result()
        for command in ("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git diff HEAD",
                        "git add -N . && git diff --binary HEAD -- . ':!patch.txt'"):
            with self.subTest(command=command):
                self.assertEqual(self.sh(command), self.sh(command, hook=False))
                subprocess.run(["git", "reset", "-q"], cwd=self.repo, check=True)
        self.assertTrue((self.repo / ".git/aci-tests/result.json").is_file())   # still waiting to be shown

    def test_new_edit_replaces_pending_run(self):
        self.sh("sed -i 's/a + b/a - b/' pkg/mod.py")
        self.sh("sed -i 's/a - b/a + b + 0/' pkg/mod.py")
        result = self.wait_result()
        self.assertEqual(result["status"].get("tests/test_mod.py::test_add"), "passed")

    def test_revert_while_baseline_runs_labels_old_failures_stale(self):
        # Ensure the bad current run finishes before reverting, while baseline
        # is still running. The old test relied on which code the child imported.
        (self.repo / "tests/test_mod.py").write_text(
            TEST_MOD + "\n\ndef test_pause():\n    import time\n    time.sleep(2)\n")
        subprocess.run(["git", "add", "tests/test_mod.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "delay"],
                       cwd=self.repo, check=True)
        self.sh("sed -i 's/a + b/a - b/' pkg/mod.py", diff=False)
        state = self.repo / ".git/aci-tests"
        job = json.loads((state / "job.json").read_text())
        for _ in range(150):
            if (state / (job["id"] + ".current.log")).is_file():
                break
            time.sleep(.1)
        else:
            self.fail("current run did not finish")
        self.assertFalse((state / "result.json").exists(), "missed baseline ordering window")
        self.sh("git checkout -- pkg/mod.py", diff=False)
        self.wait_result()
        out = self.sh("true", diff=False)
        self.assertIn("status=stale; not evidence about the current workspace", out)
        self.assertNotIn("[comparison]", out)
        self.assertNotIn("failed (new)", out)
        self.assertEqual((self.repo / "pkg/mod.py").read_text(), MOD)
        self.assertEqual(json.loads((state / "delivered.json").read_text())["freshness"], "stale")
        self.assertEqual(self.sh("echo again"), "again\n")

    def test_completed_result_detects_test_and_other_source_changes(self):
        for path in ("tests/test_mod.py", "pkg/other.py"):
            with self.subTest(path=path):
                self.sh("sed -i 's/a + b/a - b/' pkg/mod.py", diff=False)
                self.wait_result()
                # Writes outside the observed hook must still be caught at delivery.
                original = (self.repo / path).read_bytes()
                (self.repo / path).write_bytes(original + b"\n# changed after testing\n")
                out = self.sh("true", diff=False)
                self.assertIn("status=stale", out)
                self.assertNotIn("failed (new)", out)
                self.assertLessEqual(len(out), int(TESTS_ENV["ACI_TESTS_CHARS"]))
                self.sh("git checkout -- .", hook=False)
                shutil.rmtree(self.repo / ".git/aci-edit-shadow", ignore_errors=True)

    def test_unchanged_read_keeps_result_current_and_legacy_identity_is_unverified(self):
        self.sh("sed -i 's/a + b/a - b/' pkg/mod.py", diff=False)
        self.wait_result()
        self.sh("cat pkg/mod.py", hook=False)
        out = self.sh("true", diff=False)
        self.assertIn("failed (new)", out)
        state = self.repo / ".git/aci-tests"
        result = json.loads((state / "delivered.json").read_text())
        self.assertEqual(result["freshness"], "current")
        result.pop("revision")
        (state / "result.json").write_text(json.dumps(result))
        out = self.sh("true", diff=False)
        self.assertIn("status=unverified", out)
        self.assertNotIn("[comparison]", out)

    def test_test_file_edits_do_not_schedule(self):
        out = self.sh("echo '# note' >> tests/test_other.py")
        self.assertNotIn("[tests]", out)

    def test_parsers(self):
        django = ("test_a (forms_tests.tests.T) ... ok\n"
                  "test_b (forms_tests.tests.T)\nA docstring. ... FAIL\n"
                  "test_c (forms_tests.tests.T.test_c) ... ERROR\n\n"
                  "======================================================================\n"
                  "FAIL: test_b (forms_tests.tests.T)\nA docstring.\n"
                  "----------------------------------------------------------------------\n"
                  "Traceback (most recent call last):\n  File \"x.py\", line 1, in test_b\n"
                  "AssertionError: 1 != 2\n\n"
                  "----------------------------------------------------------------------\nRan 3 tests\n")
        status, reason = related_tests.parse(django)
        self.assertEqual(status, {"forms_tests.tests.T.test_a": "passed", "forms_tests.tests.T.test_b": "failed",
                                  "forms_tests.tests.T.test_c": "error"})
        self.assertEqual(reason, {"forms_tests.tests.T.test_b": "AssertionError: 1 != 2"})
        sympy = ("sympy/core/tests/test_x.py[2] \ntest_one ok\ntest_two F\n\n"
                 "________________ sympy/core/tests/test_x.py:test_two ________________\n"
                 "Traceback (most recent call last):\nAssertionError\n\n"
                 "============ tests finished: 1 passed, 1 failed, in 0.1 seconds ============\n")
        self.assertEqual(related_tests.parse(sympy), ({"sympy/core/tests/test_x.py::test_one": "passed",
                                                     "sympy/core/tests/test_x.py::test_two": "failed"},
                                                     {"sympy/core/tests/test_x.py::test_two": "AssertionError"}))


class ExecutionStatusTests(unittest.TestCase):
    def test_native_colored_output_has_same_outcomes_and_keeps_raw_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'test_sample.py').write_text(
                'def test_pass():\n    assert True\n'
                'def test_fail():\n    assert False, "expected failure"\n')
            results = []
            for color in ('no', 'yes'):
                run = subprocess.run([sys.executable, '-m', 'pytest', '-rA', '--color=' + color],
                                     cwd=tmp, text=True, capture_output=True)
                result = related_tests.outcome(run.stdout, run.returncode)
                self.assertEqual(result['log'], run.stdout)
                results.append(result)
            self.assertIn('\x1b[', results[1]['log'])
            for key in ('status', 'reason', 'outcome', 'returncode', 'detail', 'first_error'):
                self.assertEqual(results[0][key], results[1][key])
            self.assertEqual(results[1]['outcome'], 'failed')

    @staticmethod
    def result(current, baseline):
        return dict(current, sources=["pkg/mod.py"], files=["tests/test_mod.py"], command=["pytest"],
                    baseline=baseline, before=baseline["status"], log_path=".git/aci-tests/current.log")

    def test_return_code_and_completion_override_partial_passes(self):
        log = "PASSED tests/test_mod.py::test_add\n"
        for rc in (0, 1, 2, -9):
            with self.subTest(rc=rc):
                self.assertEqual(related_tests.outcome(log, rc)["outcome"], "unavailable")
        completed = log + "================ 1 passed in 0.01s ================\n"
        self.assertEqual(related_tests.outcome(completed, 0)["outcome"], "passed")
        self.assertEqual(related_tests.outcome(completed, 1)["outcome"], "unavailable")
        self.assertEqual(related_tests.outcome("no tests ran in 0.01s", 5)["outcome"], "unavailable")
        self.assertEqual(related_tests.outcome("1 skipped in 0.01s", 0)["outcome"], "unavailable")

    def test_timeout_preserves_partial_output_and_never_claims_pass(self):
        record = related_tests.run_tests([sys.executable, "-c",
            "import time; print('PASSED tests/test_x.py::test_x', flush=True); time.sleep(5)"],
            ".", dict(os.environ), 0.2)
        self.assertEqual(record["outcome"], "timeout")
        self.assertIsNone(record["returncode"])
        self.assertEqual(record["status"], {"tests/test_x.py::test_x": "passed"})
        baseline = {"status": {}, "outcome": "not_run", "detail": "current run timed out; reproduction unverified"}
        rendered = "\n".join(related_tests.render(self.result(record, baseline), 1500))
        self.assertIn("status=timeout", rendered)
        self.assertIn("status=not_run", rendered)
        self.assertIn("reproduction unverified", rendered)

    def test_first_exception_not_startup_warning_or_secondary_handler_failure(self):
        log = ("a.py:1: UserWarning: startup\n"
               "tests/test_x.py[0] Traceback (most recent call last):\n"
               '  File "a.py", line 2, in load\n    import dependency\n'
               "ModuleNotFoundError: No module named 'dependency'\n\n"
               "During handling of the above exception, another exception occurred:\n\n"
               "Traceback (most recent call last):\n"
               '  File "reporter.py", line 3, in report\n    reporter.missing\n'
               "AttributeError: reporter missing field\n")
        record = related_tests.outcome(log, 1)
        self.assertEqual(record["outcome"], "unavailable")
        self.assertEqual(record["first_error"], "ModuleNotFoundError: No module named 'dependency'")
        rendered = "\n".join(related_tests.render(self.result(record, record), 1500))
        self.assertIn("same first error reproduced before edits", rendered)
        self.assertNotIn("AttributeError", rendered)

    def test_sympy_last_line_and_duplicate_names_across_files(self):
        log = ("sympy/a/test_a.py[1]\ntest_same ok  [OK]\n"
               "sympy/b/test_b.py[1]\ntest_same E  [FAIL]\n"
               "________________________________________________________________________________\n"
               "_ sympy/b/test_b.py:test_same _\n"
               '  File "x.py", line 1, in test_same\n'
               "TypeError: incompatible\n\n"
               "=== tests finished: 1 passed, 1 exceptions, in 0.2 seconds ===\n")
        record = related_tests.outcome(log, 1)
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["status"], {"sympy/a/test_a.py::test_same": "passed",
                                           "sympy/b/test_b.py::test_same": "error"})
        self.assertEqual(record["reason"]["sympy/b/test_b.py::test_same"], "TypeError: incompatible")
        self.assertEqual(record["first_error"], "TypeError: incompatible")

    def test_sympy_import_progress_does_not_become_a_file_path(self):
        log = ('EEEEsympy/a/test_a.py[1]\ntest_same ok [OK]\n'
               'Example/test_b.py[1]\ntest_same E [FAIL]\n')
        status, _ = related_tests.parse(log)
        self.assertEqual(status, {'sympy/a/test_a.py::test_same': 'passed',
                                  'Example/test_b.py::test_same': 'error'})

    def test_baseline_missing_test_or_aborted_run_does_not_establish_new_failure(self):
        current = related_tests.outcome("FAILED tests/test_mod.py::test_add - AssertionError: bad\n"
                                        "1 failed in 0.01s", 1)
        for baseline in (related_tests.outcome("", 1), related_tests.outcome("", None, timed_out=True)):
            rendered = "\n".join(related_tests.render(self.result(current, baseline), 1500))
            self.assertIn("0 new, 0 also failing before your edits, 1 failures unverified", rendered)
            self.assertIn("failed (baseline unverified)", rendered)

    def test_long_paths_cannot_hide_execution_status_or_first_error(self):
        current = related_tests.outcome("Traceback (most recent call last):\nImportError: dependency\n", 1)
        result = self.result(current, current)
        result["sources"] = ["very_long/" * 100 + "mod.py"]
        rendered = "\n".join(related_tests.render(result, 1500)) + "\n"
        self.assertLessEqual(len(rendered), 1500)
        self.assertTrue(rendered.startswith("[tests] background run: status=unavailable"))
        self.assertIn("[first error] ImportError: dependency", rendered)
        self.assertIn("same first error reproduced before edits", rendered)
        self.assertIn("[log]", rendered)
        self.assertTrue(rendered.endswith("[tests] end; the output of this command follows\n"))

    def test_baseline_setup_failure_keeps_current_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            job = dict(id="test", sources=["pkg/mod.py"], files=[], command=["pytest"])
            (state / "job.json").write_text(json.dumps(job))
            current = related_tests.outcome("PASSED tests/test_x.py::test_x\n1 passed in 0.01s", 0)
            with patch.object(related_tests, "state_dir", return_value=state), \
                 patch.object(related_tests, "run_tests", return_value=current), \
                 patch.object(related_tests, "base_copy", side_effect=OSError("cannot copy")), \
                 patch.dict(os.environ, ACI_TESTS_TIMEOUT="1"):
                related_tests.run("test")
            result = json.loads((state / "result.json").read_text())
            self.assertEqual(result["outcome"], "passed")
            self.assertEqual(result["baseline"]["outcome"], "unavailable")
            self.assertIn("cannot copy", result["baseline"]["first_error"])


class TestsConfigTests(unittest.TestCase):
    def merged(self, condition):
        from minisweagent.config import get_config_from_spec
        from minisweagent.utils.serialize import recursive_merge
        return recursive_merge(*(get_config_from_spec(str(s)) for s in
                                 ["swebench.yaml", EXTRA / "aci-common.yaml", EXTRA / f"aci-{condition}.yaml"]))

    def test_slcat_preserves_baseline_instructions_with_the_hook(self):
        from jinja2 import StrictUndefined, Template
        base, v = self.merged("baseline"), self.merged("slcat")
        render = lambda c: Template(c["agent"]["system_template"], undefined=StrictUndefined).render(
            env=c["environment"]["env"])
        self.assertEqual(render(v), render(base))
        self.assertEqual(v["environment"]["env"]["ACI_EDIT_TESTS"], "1")
        self.assertEqual(v["environment"]["env"]["ACI_EDIT_DIFF"], "0")
        self.assertEqual(v["run"], base["run"])






if __name__ == "__main__":
    unittest.main()
