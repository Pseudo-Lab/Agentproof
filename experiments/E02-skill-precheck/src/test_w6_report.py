"""Offline checks for the W6 report's denominators and uncertainty."""
import unittest
import w6_report as W


class ReportTests(unittest.TestCase):
    def test_api_error_remains_in_denominator_and_cost(self):
        rows = [dict(trial_id='a', status='success', cost_usd=.2),
                dict(trial_id='b', status='error', cost_usd=.1)]
        self.assertEqual(W.summarize_rows(rows),
                         dict(success=1, n=2, errors=1, cost_usd=.3))

    def test_cluster_difference_weights_tasks_equally(self):
        rows = [dict(task='large', cond='B', status='failure')] * 9
        rows += [dict(task='large', cond='C2', status='success')] * 9
        rows += [dict(task='small', cond='B', status='success'),
                 dict(task='small', cond='C2', status='failure')]
        out = W.cluster_difference(rows, 'C2', 'B')
        self.assertEqual(out['diff_pp'], 0)
        self.assertEqual(out['per_task_pp'], dict(large=100, small=-100))
        self.assertEqual(out['ci95_pp'], [-100, 100])

    def test_missing_arm_is_not_silently_dropped(self):
        with self.assertRaises(ValueError):
            W.cluster_difference([dict(task='x', cond='B', status='success')], 'C2', 'B')

    def test_duplicate_trial_rejected(self):
        with self.assertRaises(ValueError):
            W.validate_rows([dict(trial_id='a'), dict(trial_id='a')])


if __name__ == '__main__':
    unittest.main()
