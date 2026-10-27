"""Synthetic mapping checks, not additional model trials or an evaluator test."""
import unittest
from export_trials import classify


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.report = {"resolved_ids": ["fixed"], "unresolved_ids": ["wrong"],
                       "empty_patch_ids": ["empty"], "error_ids": ["broken"]}

    def test_resolved(self):
        self.assertEqual(classify("fixed", self.report, "Submitted"), ("success", 1))

    def test_wrong_and_empty_stay_in_denominator(self):
        for task in ["wrong", "empty"]:
            self.assertEqual(classify(task, self.report, "Submitted"), ("failure", 0))

    def test_evaluator_error(self):
        self.assertEqual(classify("broken", self.report, "Submitted"), ("error", 0))

    def test_timeout_is_not_ordinary_failure(self):
        self.assertEqual(classify("wrong", self.report, "TimeExceeded"), ("timeout", 0))

    def test_recovered_success_keeps_timeout_status_and_score(self):
        self.assertEqual(classify("fixed", self.report, "TimeExceeded"), ("timeout", 1))

    def test_missing_outcome_is_not_invented(self):
        with self.assertRaises(ValueError):
            classify("missing", self.report, "Submitted")


if __name__ == "__main__":
    unittest.main()
