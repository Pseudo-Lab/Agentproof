"""Offline checks for localization_metrics (no Docker, synthetic repository)."""
import unittest

from localization_metrics import Source, gold_blocks, trial_metrics, visible_lines

LINES = [f"    value_{i} = compute({i})" for i in range(1, 41)]
SOURCE = Source({"pkg/mod.py"}, lambda path: LINES)
PATCH = """diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -9,3 +9,4 @@
     value_9 = compute(9)
+    extra = 1
     value_10 = compute(10)
     value_11 = compute(11)
@@ -19,3 +20,3 @@
     value_19 = compute(19)
-    value_20 = compute(20)
+    value_20 = compute(21)
     value_21 = compute(21)
"""


def output(*segments):
    return "<returncode>0</returncode>\n" + "".join(segments)


class GoldTest(unittest.TestCase):
    def test_replacement_and_insertion(self):
        self.assertEqual(gold_blocks(PATCH), {"pkg/mod.py": [{9, 10}, {20}]})


class VisibilityTest(unittest.TestCase):
    def test_truncated_cat_hides_middle(self):
        head = "\n".join(LINES[:5])
        tail = "\n".join(LINES[35:])
        content = output(f"<output_head>\n{head}\n</output_head>\n<elided_chars>\n9\n</elided_chars>\n",
                         f"<output_tail>\n{tail}\n</output_tail>")
        seen = visible_lines("cat pkg/mod.py", content, SOURCE)
        self.assertEqual({n for _, n in seen}, set(range(1, 6)) | set(range(36, 41)))

    def test_grep_numbers_must_match_source_text(self):
        content = output("<output>\n20:    value_20 = compute(20)\n7:    wrong text here\n</output>")
        self.assertEqual(visible_lines("grep -n value pkg/mod.py", content, SOURCE), {("pkg/mod.py", 20)})

    def test_numbered_snippet_under_file_tag(self):
        content = output("<output>\n<file>pkg/mod.py</file>\n<code>\n19 " + LINES[18] +
                         "\n20 " + LINES[19] + "\n</code>\n</output>")
        seen = visible_lines("get_code_around_line pkg/mod.py 20 1", content, SOURCE)
        self.assertEqual(seen, {("pkg/mod.py", 19), ("pkg/mod.py", 20)})

    def test_unnumbered_excerpt_aligns_to_base_lines(self):
        content = output("<output>\n" + "\n".join(LINES[16:22]) + "\n</output>")
        seen = visible_lines("sed -n '17,22p' pkg/mod.py", content, SOURCE)
        self.assertEqual({n for _, n in seen}, set(range(17, 23)))


class BlankEdgeTest(unittest.TestCase):
    def test_tag_newlines_are_not_counted_as_blank_base_lines(self):
        lines = ["def f():", "", "    return compute_value(1)", "    # trailing note", ""]
        source = Source({"m.py"}, lambda path: lines)
        content = output("<output>\n" + "\n".join(lines[2:4]) + "\n</output>")
        self.assertEqual(visible_lines("sed -n '3,4p' m.py", content, source), {("m.py", 3), ("m.py", 4)})


class TrialTest(unittest.TestCase):
    def test_first_hit_precision_and_cost(self):
        steps = [("sed -n '1,5p' pkg/mod.py", output("<output>\n" + "\n".join(LINES[:5]) + "\n</output>")),
                 ("sed -n '18,21p' pkg/mod.py", output("<output>\n" + "\n".join(LINES[17:21]) + "\n</output>"))]
        metrics = trial_metrics(steps, PATCH, SOURCE)
        self.assertEqual(metrics["steps_to_locate"], 2)
        self.assertEqual(metrics["lines_to_locate"], 9)
        self.assertEqual(metrics["hit_precision"], 0.25)
        self.assertEqual(metrics["location_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
