"""Compare S/U adapters with upstream implementations; see README test setup."""

import ast
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest



ROOT = Path(__file__).resolve().parents[2]


BUNDLES = Path(os.environ["ACI_TEST_BUNDLES"])
SEARCH_PYTHON = str(BUNDLES / "search/.venv/bin/python")
SKELETON_PYTHON = str(BUNDLES / "understanding/agentless/.venv/bin/python")
READER_PYTHON = str(BUNDLES / "understanding/codestruct/.venv/bin/python")
READER_SOURCE = Path("SWE-agent/tools/ast_read/bin/readCode")


class SearchUnderstandingTests(unittest.TestCase):
    bundles = BUNDLES

    def test_vendored_sources_and_licenses_are_unchanged(self):
        for layer in ("search", "understanding/agentless", "understanding/codestruct"):
            for project in (ROOT / "tools" / layer / "upstream").iterdir():
                for source in project.rglob("*"):
                    if source.is_file() and "__pycache__" not in source.parts:
                        original = ROOT / "external" / project.name / source.relative_to(project)
                        if project.name == "CodeStruct" and source.relative_to(project) == READER_SOURCE:
                            # The sole reader change is tested by applying the recorded patch.
                            continue
                        self.assertEqual(source.read_bytes(), original.read_bytes(), str(source))

    def test_reader_equals_original_plus_recorded_utf8_patch(self):
        with tempfile.TemporaryDirectory(prefix="aci-reader-patch-") as temporary:
            target = Path(temporary) / 'bin/readCode'
            target.parent.mkdir()
            shutil.copy2(ROOT / 'external/CodeStruct' / READER_SOURCE, target)
            patch = ROOT / 'tools/understanding/codestruct/patches/0001-fix-utf8-node-text.patch'
            subprocess.run(['git', 'apply', str(patch)], cwd=temporary, check=True, capture_output=True)
            self.assertEqual(target.read_bytes(),
                             (BUNDLES / 'understanding/codestruct/upstream/CodeStruct' / READER_SOURCE).read_bytes())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aci-lens-su-repo-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "package").mkdir()
        (self.repo / "package/service.py").write_text(
            "LIMIT = 5\n\nclass Service:\n"
            "    def execute(self, value):\n"
            "        return value + LIMIT\n\n"
            "def original_symbol():\n    return 'before-edit'\n"
        )

    def run_search(self, operation, *args, cwd=None):
        return subprocess.run(
            [str(self.bundles / "search/bin" / operation), *args],
            cwd=cwd or self.repo, capture_output=True, text=True, timeout=30,
        )

    def run_original_search(self, operation, *args):
        return subprocess.run(
            [SEARCH_PYTHON, "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); "
             "from app.search.search_backend import SearchBackend; "
             "print(getattr(SearchBackend(sys.argv[2]), sys.argv[3])(*sys.argv[4:])[0])",
             str(ROOT / "external/auto-code-rover"), str(self.repo), operation, *args],
            cwd=self.repo, capture_output=True, text=True, timeout=30,
        )

    def run_skeleton(self, path):
        return subprocess.run(
            [str(self.bundles / "understanding/agentless/bin/agentless_skeleton"), str(path)],
            cwd=self.repo, capture_output=True, text=True, timeout=30,
        )

    def run_original_skeleton(self, path):
        return subprocess.run(
            [SKELETON_PYTHON, "-c",
             "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
             "from agentless.util.compress_file import get_skeleton; "
             "print(get_skeleton(Path(sys.argv[2]).read_text(), compress_assign=True), end='')",
             str(ROOT / "external/Agentless"), str(path)],
            cwd=self.repo, capture_output=True, text=True, timeout=30,
        )

    def run_reader(self, *arguments, original=False):
        command = ([READER_PYTHON, str(ROOT / 'external/CodeStruct' / READER_SOURCE)] if original
                   else [str(BUNDLES / 'understanding/codestruct/bin/readCode')])
        result = subprocess.run([*command, *map(str, arguments)], cwd=self.repo,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def test_reader_raw_selector_large_summary_and_ranges_match_upstream(self):
        large = self.repo / 'large.py'
        large.write_text('def large_symbol():\n    return 42\n' + '# filler\n' * 1500)
        (self.repo / 'notes.txt').write_text('café雪😀\nsecond line\nlast line\n')
        for arguments, expected in [
            (('package/service.py',), 'return value + LIMIT'),
            (('package/service.py', '--selector', 'Service.execute'), 'return value + LIMIT'),
            (('large.py',), 'Signatures in large.py'),
            (('large.py', '--selector', 'large_symbol'), 'return 42'),
            (('notes.txt', '--line-start', '1', '--line-end', '2'), 'café雪😀'),
        ]:
            with self.subTest(arguments=arguments):
                output = self.run_reader(*arguments)
                self.assertEqual(output, self.run_reader(*arguments, original=True))
                self.assertIn(expected, output)
        self.assertNotIn('return 42', self.run_reader('large.py'))
        self.assertNotIn('last line', self.run_reader('notes.txt', '--line-start', '1', '--line-end', '2'))
        large.write_text(large.read_text().replace('large_symbol', 'renamed_symbol'))
        self.assertIn('def renamed_symbol', self.run_reader(large, '--selector', 'renamed_symbol'))

    def test_reader_unicode_selector_does_not_truncate_or_include_next_statement(self):
        fixtures = [
            ('def answer():\n    return "é雪😀"', 'answer'),
            ('class Service:\n    def answer(self):\n        return "é雪😀"', 'Service'),
            ('class Service:\n    def answer(self):\n        return "é雪😀"', 'Service.answer'),
        ]
        for body, selector in fixtures:
            with self.subTest(selector=selector):
                target = self.repo / 'unicode.py'
                target.write_text('# café雪😀\n' + body + '\n\nSENTINEL = 7\n')
                expected = body if selector != 'Service.answer' else body.split('\n', 1)[1].lstrip()
                before = self.run_reader(target, '--selector', selector, original=True)
                output = self.run_reader(target, '--selector', selector)
                self.assertNotIn(expected, before, 'Fixture must reproduce the original defect')
                self.assertIn(expected, output)
                self.assertNotIn('SENTINEL', output)
                # Reading a small file without selection never needed this correction.
                self.assertEqual(self.run_reader(target), self.run_reader(target, original=True))

    def test_search_sees_edits_and_resolves_repository_from_nested_cwd(self):
        first = self.run_search("search_method", "original_symbol", cwd=self.repo / "package")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("before-edit", first.stdout)
        file = self.repo / "package/service.py"
        file.write_text(file.read_text().replace("original_symbol", "renamed_symbol")
                        .replace("before-edit", "after-edit"))
        second = self.run_search("search_method", "renamed_symbol")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("after-edit", second.stdout)
        old = self.run_search("search_method", "original_symbol")
        self.assertEqual(old.returncode, 0, old.stderr)
        self.assertNotIn("<code>", old.stdout)

    def test_search_help_preserves_original_names_arguments_and_descriptions(self):
        tree = ast.parse((ROOT / "external/auto-code-rover/app/search/search_backend.py").read_text())
        backend = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SearchBackend")
        methods = {node.name: node for node in backend.body if isinstance(node, ast.FunctionDef)}
        expected = {"search_class", "search_class_in_file", "search_method", "search_method_in_file",
                    "search_method_in_class", "search_code", "search_code_in_file", "get_code_around_line"}
        self.assertEqual({path.name for path in (self.bundles / "search/bin").iterdir()}, expected)
        for name in expected:
            result = self.run_search(name, "--help")
            self.assertEqual(result.returncode, 0, result.stderr)
            for arg in methods[name].args.args:
                if arg.arg != "self":
                    self.assertIn(arg.arg, result.stdout)
            self.assertIn(" ".join(ast.get_docstring(methods[name]).split()), " ".join(result.stdout.split()))

    def test_all_eight_search_launchers_match_direct_upstream_output(self):
        cases = [
            ("search_class", "Service"),
            ("search_class_in_file", "Service", "package/service.py"),
            ("search_method", "original_symbol"),
            ("search_method_in_file", "execute", "service.py"),
            ("search_method_in_class", "execute", "Service"),
            ("search_code", "value + LIMIT"),
            ("search_code_in_file", "value + LIMIT", "service.py"),
            ("get_code_around_line", "package/service.py", "5", "1"),
            ("get_code_around_line", "package/service.py", "1", "0"),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_search(*arguments)
                original = self.run_original_search(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(original.returncode, 0, original.stderr)
                self.assertIn("package/service.py", result.stdout)
                self.assertEqual(result.stdout, original.stdout)
                self.assertIn("<file>package/service.py</file>", result.stdout)
        invalid = self.run_search("search_method_in_file", "execute")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("file_name", invalid.stderr)
        self.assertIn("required", invalid.stderr)
        bad_line = self.run_search("get_code_around_line", "service.py", "invalid", "1")
        original_bad_line = self.run_original_search("get_code_around_line", "service.py", "invalid", "1")
        self.assertEqual(bad_line.returncode, original_bad_line.returncode)
        self.assertEqual(bad_line.stdout, original_bad_line.stdout)

    def test_search_preserves_literal_leading_hyphen_queries(self):
        (self.repo / "negation.py").write_text("def negate(value):\n    return -value\n")
        for arguments in (("search_code", "-value"),
                          ("search_code_in_file", "-value", "negation.py")):
            with self.subTest(arguments=arguments):
                result = self.run_search(arguments[0], "--", *arguments[1:])
                original = self.run_original_search(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(original.returncode, 0, original.stderr)
                self.assertIn("return -value", result.stdout)
                self.assertEqual(result.stdout, original.stdout)

    def test_prepared_index_is_reused_and_tracks_added_deleted_and_same_size_edits(self):
        cache = self.bundles / "search/.cache"
        before = set(cache.rglob("output.pkl"))
        subprocess.run([SEARCH_PYTHON, str(self.bundles / "search/search_dispatch.py"),
                        "--prepare", str(self.repo)], check=True, timeout=30)
        prepared = set(cache.rglob("output.pkl")) - before
        self.assertEqual(len(prepared), 1)
        stamp = next(iter(prepared)).stat().st_mtime_ns
        for _ in range(2):
            found = self.run_search("search_method", "original_symbol")
            self.assertIn("before-edit", found.stdout)
        self.assertEqual(set(cache.rglob("output.pkl")) - before, prepared)
        self.assertEqual(next(iter(prepared)).stat().st_mtime_ns, stamp)

        # Preserve mtime and size: ctime must still invalidate the saved index.
        source = self.repo / "package/service.py"
        old_stat = source.stat()
        source.write_text(source.read_text().replace("original_symbol", "replaced_symbol"))
        os.utime(source, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        self.assertIn("<code>", self.run_search("search_method", "replaced_symbol").stdout)
        self.assertNotIn("<code>", self.run_search("search_method", "original_symbol").stdout)
        added = self.repo / "package/added.py"
        added.write_text("def added_symbol():\n    return 42\n")
        self.assertIn("return 42", self.run_search("search_method", "added_symbol").stdout)
        added.unlink()
        self.assertNotIn("<code>", self.run_search("search_method", "added_symbol").stdout)

    def test_search_preserves_upstream_test_exclusion_and_parse_failure_behavior(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_service.py").write_text("def hidden_test_only():\n    pass\n")
        (self.repo / "broken.py").write_text("def invalid(:\n")
        result = self.run_search("search_method", "hidden_test_only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("<code>", result.stdout)
        valid = self.run_search("search_method", "execute")
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertIn("return value + LIMIT", valid.stdout)

    def test_skeleton_keeps_structure_and_constants_but_omits_function_body(self):
        result = self.run_skeleton("package/service.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("LIMIT = 5", "class Service:", "def execute(self, value):", "..."):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("return value + LIMIT", result.stdout)
        self.assertNotIn("before-edit", result.stdout)
        original = self.run_original_skeleton("package/service.py")
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertEqual(result.stdout, original.stdout)
        self.assertIn("def execute(self, value):\n...\n", result.stdout)
        file = self.repo / "package/service.py"
        file.write_text(file.read_text().replace("original_symbol", "new_symbol"))
        self.assertIn("def new_symbol", self.run_skeleton(file).stdout)

    def test_skeleton_compresses_long_assignments_and_preserves_raw_parse_fallback(self):
        file = self.repo / "large.py"
        file.write_text("VALUES = [\n" + "".join(f"    {n},\n" for n in range(80)) + "]\n")
        result = self.run_skeleton(file)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("...", result.stdout)
        self.assertNotIn("    40,", result.stdout)
        original = self.run_original_skeleton(file)
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertEqual(result.stdout, original.stdout)
        file.write_text("def broken(:\n")
        fallback = self.run_skeleton(file)
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertEqual(fallback.stdout, file.read_text())


if __name__ == "__main__":
    unittest.main()
