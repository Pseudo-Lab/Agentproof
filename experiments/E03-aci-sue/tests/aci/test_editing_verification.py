"""Real CodeStruct CLI fixtures, prepared as documented in README without model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EDIT_BUNDLE = Path(os.environ["ACI_TEST_BUNDLES"]) / "editing"
UPSTREAM_EDITOR = ROOT / "external/CodeStruct/SWE-agent/tools/ast_edit"
PATCH_DIR = ROOT / "tools/editing/patches"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CodeStructIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "example.py"
        self.original = "def answer():\n    return 1\n"
        self.target.write_text(self.original)

    def edit(self, replacement):
        return subprocess.run(["bash", str(EDIT_BUNDLE / "bin/editCode"), str(self.target),
                               "replace_node", "answer", "--replacement", replacement],
                              capture_output=True, text=True, timeout=30)

    def test_editor_changes_a_selected_function(self):
        result = self.edit("def answer():\n    return 42")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Successfully executed replace_node", result.stdout)
        namespace = {}
        exec(compile(self.target.read_text(), str(self.target), "exec"), namespace)
        self.assertEqual(namespace["answer"](), 42)
        self.assertNotIn("fallback", result.stdout.lower())

    def test_editor_retains_original_syntax_rejection_without_mutation(self):
        result = self.edit("def answer(:\n    return 42")
        # The retained upstream CLI intentionally communicates errors in stdout
        # and returns 0; do not mistake that status for a successful edit.
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Error:", result.stdout)
        self.assertIn("syntax errors", result.stdout)
        self.assertEqual(self.target.read_text(), self.original)

    def test_runtime_is_exactly_pinned_source_plus_recorded_patch(self):
        manifest = json.loads((PATCH_DIR / "manifest.json").read_text())
        for entry in manifest["patches"]:
            self.assertEqual(sha256(PATCH_DIR / entry["patch"]), entry["patch_sha256"])
            self.assertEqual(sha256(UPSTREAM_EDITOR / entry["target"]), entry["before_sha256"])
            self.assertEqual(sha256(EDIT_BUNDLE / "upstream" / entry["target"]), entry["after_sha256"])
        for source in (EDIT_BUNDLE / "upstream/lib").rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts:
                self.assertEqual(
                    source.read_bytes(),
                    (UPSTREAM_EDITOR / "lib" / source.relative_to(EDIT_BUNDLE / "upstream/lib")).read_bytes(),
                )
        for command in ('str_replace', 'create_file'):
            original = ROOT / 'external/CodeStruct/SWE-agent/tools/str_replace/bin' / command
            self.assertEqual((EDIT_BUNDLE / 'upstream/bin' / command).read_bytes(), original.read_bytes())

    def test_text_replacement_and_file_creation_match_original_clis(self):
        cases = [
            ('str_replace', 'example.py', self.original, ('return 1', 'return 42'),
             'def answer():\n    return 42\n'),
            ('str_replace', 'example.py', 'repeat\nrepeat\n', ('repeat', 'changed'), 'repeat\nrepeat\n'),
            ('str_replace', 'example.py', self.original, ('missing text', 'changed'), self.original),
            ('str_replace', 'example.py', '# café雪😀\n' + self.original, ('# café雪😀\n',), self.original),
            ('create_file', 'nested/new.py', None, ('# café雪😀\nvalue = 42\n',), '# café雪😀\nvalue = 42\n'),
            ('create_file', 'example.py', self.original, ('replacement\n',), 'replacement\n'),
        ]
        for command, name, initial, arguments, expected in cases:
            with self.subTest(command=command, arguments=arguments):
                observations = []
                for original in (True, False):
                    with tempfile.TemporaryDirectory(prefix='aci-edit-cli-') as folder:
                        path = Path(folder) / name
                        if initial is not None:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text(initial)
                        executable = ([str(EDIT_BUNDLE / '.venv/bin/python'),
                                       str(ROOT / 'external/CodeStruct/SWE-agent/tools/str_replace/bin' / command)]
                                      if original else [str(EDIT_BUNDLE / 'bin' / command)])
                        result = subprocess.run([*executable, name, *arguments], cwd=folder,
                                                capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(path.read_text(), expected)
                        observations.append((result.returncode, result.stdout.replace(folder, '<fixture>'),
                                             result.stderr.replace(folder, '<fixture>'), path.read_bytes()))
                self.assertEqual(observations[0], observations[1])


class CodeStructUtf8PatchTests(unittest.TestCase):
    patched = EDIT_BUNDLE / "upstream/bin/editCode"
    python = EDIT_BUNDLE / ".venv/bin/python"

    def run_editor(self, code, arguments, *, patched=True):
        with tempfile.TemporaryDirectory(prefix="aci-codestruct-fixture-") as directory:
            target = Path(directory) / "fixture.py"
            target.write_text(code)
            executable = self.patched if patched else UPSTREAM_EDITOR / "bin/editCode"
            result = subprocess.run([str(self.python), str(executable), str(target), *arguments],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout, target.read_text()

    def assert_unicode_fix(self, code, arguments, expected):
        original_output, original_result = self.run_editor(code, arguments, patched=False)
        self.assertNotEqual(original_result, expected, "Fixture must expose the original defect")
        output, actual = self.run_editor(code, arguments)
        self.assertIn("Successfully executed", output)
        self.assertEqual(actual, expected, original_output)
        compile(actual, "patched-fixture.py", "exec")

    def test_replace_unicode_inside_node_preserves_following_statement(self):
        suffix = "\nSENTINEL = 7\n\n"
        original = 'def target():\n    return "' + "é" * 14 + '"' + suffix
        replacement = "def target():\n    return 42"
        self.assert_unicode_fix(original, ["replace_node", "target", "--replacement", replacement],
                                replacement + suffix)

    def test_replace_unicode_before_target_and_scoped_method(self):
        fixtures = [
            ("# café雪😀\n\ndef target():\n    return 1\n\nSENTINEL = 7\n",
             "target", "def target():\n    return 42",
             "# café雪😀\n\ndef target():\n    return 42\n\nSENTINEL = 7\n"),
            ('# café雪😀\nclass Example:\n    LABEL = "é雪"\n'
             '    def target(self):\n        return "é雪😀"\n\nSENTINEL = 7\n',
             "Example.target", "def target(self):\n    return 42",
             '# café雪😀\nclass Example:\n    LABEL = "é雪"\n'
             '    def target(self):\n        return 42\n\nSENTINEL = 7\n'),
        ]
        for original, selector, replacement, expected in fixtures:
            with self.subTest(selector=selector):
                self.assert_unicode_fix(original, ["replace_node", selector, "--replacement", replacement], expected)

    def test_insert_after_unicode_node_keeps_correct_position(self):
        target = 'def target():\n    return "' + "é" * 14 + '"\n'
        suffix = "SENTINEL = 7\n\n"
        replacement = "def added():\n    return 42"
        self.assert_unicode_fix(target + suffix, ["insert_node", "target", "--replacement", replacement],
                                target + "\n" + replacement + "\n" + suffix)

    def test_insert_method_with_unicode_keeps_class_and_neighboring_code(self):
        target = '# café雪😀\nclass Example:\n    def target(self):\n        return "é雪😀"'
        suffix = "\n\nSENTINEL = 7\n"
        replacement = "def added(self):\n    return 42"
        self.assert_unicode_fix(target + suffix, ["insert_node", "Example", "--replacement", replacement],
                                target + "\n\n    def added(self):\n        return 42" + suffix)

    def test_delete_unicode_before_and_inside_node_preserves_neighbors(self):
        fixtures = [
            ('def target():\n    return "' + "é" * 14 + '"\nSENTINEL = 7\n\n', "SENTINEL = 7\n\n"),
            ('# café雪😀\n\ndef target():\n    return "é雪😀"\n\nSENTINEL = 7\n',
             "# café雪😀\n\n\nSENTINEL = 7\n"),
        ]
        for original, expected in fixtures:
            with self.subTest(original=original):
                self.assert_unicode_fix(original, ["delete_node", "target"], expected)

    def test_replace_in_node_cannot_escape_node_after_unicode(self):
        original = 'def target():\n    return "' + "é" * 14 + '"\nSENTINEL = 7\n\n'
        arguments = ["replace_in_node", "target", "--old_str", "SENTINEL = 7", "--new_str", "SENTINEL = 99"]
        old_output, old_result = self.run_editor(original, arguments, patched=False)
        self.assertIn("Successfully executed", old_output)
        self.assertIn("SENTINEL = 99", old_result)
        output, actual = self.run_editor(original, arguments)
        self.assertIn("not found in target node", output)
        self.assertEqual(actual, original)

    def test_ascii_and_unicode_after_target_match_original_behavior(self):
        for suffix in ("SENTINEL = 7\n", 'SENTINEL = "é雪😀"\n'):
            original = "def target():\n    return 1\n\n" + suffix
            cases = [
                ["replace_node", "target", "--replacement", "def target():\n    return 42"],
                ["insert_node", "target", "--replacement", "def added():\n    return 42"],
                ["delete_node", "target"],
                ["replace_in_node", "target", "--old_str", "return 1", "--new_str", "return 42"],
            ]
            for arguments in cases:
                with self.subTest(operation=arguments[0], suffix=suffix):
                    before = self.run_editor(original, arguments, patched=False)
                    after = self.run_editor(original, arguments)
                    self.assertIn("Successfully executed", before[0])
                    self.assertEqual(after, before)
