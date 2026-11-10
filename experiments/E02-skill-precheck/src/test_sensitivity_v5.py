"""Post-hoc offline sensitivity checks, independent of model execution."""
import unittest
import sensitivity_v5 as S


def row(task,seed,cond,success):
    return dict(task=task,input_seed=seed,cond=cond,env='E1',loc='L3',
                status='success' if success else 'failure')


class SensitivityTests(unittest.TestCase):
    def test_exact_discordance_uses_paired_inputs(self):
        rows=[]
        for seed in range(5):
            rows += [row('a',seed,'C2',seed<4),row('a',seed,'N',seed==4)]
        out=S.paired_contrast(rows,'C2','N')
        self.assertEqual(out['a_only'],4);self.assertEqual(out['b_only'],1)
        self.assertEqual(out['n_pairs'],5)
        self.assertEqual(out['exact_two_sided_p'],.375)

    def test_four_discordances_are_not_five_task_families(self):
        rows=[]
        for seed in range(4):rows += [row('same',seed,'C2',True),row('same',seed,'N',False)]
        out=S.paired_contrast(rows,'C2','N')
        self.assertEqual(out['task_families'],1)
        self.assertEqual(out['exact_two_sided_p'],.125)

    def test_missing_or_duplicate_pair_is_rejected(self):
        with self.assertRaises(ValueError):S.paired_contrast([row('a',1,'C2',True)],'C2','N')
        with self.assertRaises(ValueError):
            S.paired_contrast([row('a',1,'C2',True),row('a',1,'C2',False),row('a',1,'N',False)],'C2','N')

    def test_omitting_positive_task_reverses_average(self):
        out=S.leave_one_out({'graph':80.,'csv':-20.,'events':0.})
        self.assertEqual(out['full_mean_pp'],20.)
        self.assertEqual(out['without']['graph'],-10.)
        self.assertEqual(out['without']['csv'],40.)
        self.assertEqual(out['without']['events'],30.)

if __name__=='__main__':unittest.main()
