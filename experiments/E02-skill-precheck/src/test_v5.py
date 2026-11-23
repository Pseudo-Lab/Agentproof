import json
import tempfile
import threading
import unittest
from pathlib import Path
import agent as A
import tasks as T
import agent_v5 as V


class V5Tests(unittest.TestCase):
    def test_reservations_prevent_parallel_overspend(self):
        budget=V.Budget(1)
        tickets=[]
        def reserve():
            ticket=budget.reserve(.6)
            if ticket is not None:tickets.append(ticket)
        threads=[threading.Thread(target=reserve) for _ in range(8)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(tickets),1)
        budget.settle(tickets[0],.2)
        self.assertIsNotNone(budget.reserve(.7))
        self.assertIsNone(budget.reserve(.2))

    def test_unknown_billing_retains_worst_case_charge(self):
        budget=V.Budget(1)
        ticket=budget.reserve(.7);budget.unknown(ticket)
        self.assertEqual(budget.spent,.7)
        self.assertIsNone(budget.reserve(.4))

    def test_mixed_graph_error_is_not_called_skill_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('graph','E1','L3',33,Path(tmp)/'ws')
            T.solve('graph','E1',ws,'literal')
            self.assertEqual(V.diagnose('graph','E1',33,ws)['label'],'skill_consistent_mismatch')
            f=ws/T.OUTPUT_FILE['graph'];data=json.loads(f.read_text());data['nodes']=[]
            f.write_text(json.dumps(data))
            self.assertEqual(V.diagnose('graph','E1',33,ws)['label'],'other_error')

    def test_correct_and_missing_output_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('events','E1','L3',33,Path(tmp)/'ws')
            self.assertEqual(V.diagnose('events','E1',33,ws)['label'],'missing_output')
            T.solve('events','E1',ws,'oracle')
            self.assertEqual(V.diagnose('events','E1',33,ws)['label'],'correct')

    def test_post_check_archives_wrong_output_before_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('events','E1','L3',33,Path(tmp)/'ws')
            def solve(mode):
                T.solve('events','E1',ws,mode)
                return T.OUTPUT_FILE['events'],(ws/T.OUTPUT_FILE['events']).read_text()
            client=Scripted(solve)
            snapshots=[]
            def snapshot():
                value=V.diagnose('events','E1',33,ws)
                snapshots.append(value)
                return value
            res=V.run_agent(client,CONFIG,ws,'skill','V',V.Budget(2),snapshot)
            self.assertEqual(res['stop_reason'],'agent_finished')
            self.assertEqual(res['pre_hooks'],1);self.assertEqual(res['post_hooks'],1)
            self.assertEqual(len(snapshots),1)
            self.assertEqual(snapshots[0]['label'],'skill_consistent_mismatch')
            self.assertEqual(V.diagnose('events','E1',33,ws)['label'],'correct')

    def test_neutral_post_is_one_opportunity_without_forced_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('events','E1','L3',33,Path(tmp)/'ws')
            def solve(mode):
                T.solve('events','E1',ws,mode)
                return T.OUTPUT_FILE['events'],(ws/T.OUTPUT_FILE['events']).read_text()
            for cond in ('B','N'):
                res=V.run_agent(Scripted(solve),CONFIG,ws,'skill',cond,V.Budget(2),lambda:V.diagnose('events','E1',33,ws))
                self.assertEqual(res['post_hooks'],int(cond=='N'))
                self.assertEqual(res['stop_reason'],'agent_finished')
                self.assertEqual(V.diagnose('events','E1',33,ws)['label'],'skill_consistent_mismatch')


CONFIG={'model':'offline-test','reasoning_effort':'low','price_input_per_mtok':.75,'price_output_per_mtok':4.5,
        'limits':{'max_model_requests':20,'max_tool_calls':20,'wall_clock_s':300,
                  'max_cumulative_input_tokens':150000,'max_cumulative_output_tokens':20000}}

class Scripted:
    """Only models the transport boundary; the real agent executes tools and grades files."""
    def __init__(self,solve):self.responses=self;self.solve=solve;self.n=0
    def create(self,**kw):
        self.n+=1;items=kw['input']
        calls=[i for i in items if i.get('type')=='function_call']
        posts=[i for i in items if i.get('role')=='developer' and i.get('content') in (V.POST,V.NEUTRAL_POST)]
        if not calls:out=[dict(type='function_call',call_id=str(self.n),name='read_skill',arguments='{}')]
        elif len(calls)==1 or (posts and posts[-1]['content']==V.POST and len(calls)==2):
            path,text=self.solve('oracle' if posts else 'literal')
            out=[dict(type='function_call',call_id=str(self.n),name='write_file',arguments=json.dumps(dict(path=path,content=text)))]
        else:out=[dict(type='message',role='assistant',content=[dict(type='output_text',text='done')])]
        return A._Obj(id=str(self.n),status='completed',output=out,output_text='done',
                      usage=A._Obj(input_tokens=100,output_tokens=20))


class AnalysisTests(unittest.TestCase):
    def test_transition_does_not_call_mixed_error_a_premise_correction(self):
        import analyze_v5
        rows=[dict(task='events',env='E1',loc='L3',cond='V',status='success',cost_usd=.1,
                   before_post={'label':'other_error'},final={'label':'correct'})]
        out=analyze_v5.analyze(rows,{'tasks':['events'],'envs':['E0','E1'],
                                     'input_seeds':[1,2],'hidden_conditions':['B','N','C2','V','P'],
                                     'pointed_conditions':['B']})
        self.assertEqual(out['transitions']['V|E1']['other_error -> correct'],1)
        self.assertNotIn('skill_consistent_mismatch -> correct',out['transitions']['V|E1'])
        self.assertEqual(out['transitions_by_task']['events|V|E1']['other_error -> correct'],1)
        self.assertFalse(out['complete'])
        self.assertIsNone(out['comparisons']['C2-N|E1']['effect'])

class MalformedOutputTests(unittest.TestCase):
    def test_nested_graph_value_is_recorded_without_losing_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('graph','E1','L3',44,Path(tmp)/'ws')
            T.solve('graph','E1',ws,'oracle')
            p=ws/T.OUTPUT_FILE['graph'];data=json.loads(p.read_text())
            data['edges'][0]['source']=[];p.write_text(json.dumps(data))
            diag=V.diagnose('graph','E1',44,ws)
            self.assertEqual(diag['label'],'other_error')
            self.assertFalse(diag['target_pass']);self.assertFalse(diag['other_pass'])
            self.assertIn('TypeError',diag['diagnostic_errors'][0])

class DeadlineTests(unittest.TestCase):
    def test_late_response_is_not_accepted_as_success(self):
        import time
        class Slow(Scripted):
            def create(self,**kw):
                time.sleep(.02)
                return super().create(**kw)
        with tempfile.TemporaryDirectory() as tmp:
            cfg=json.loads(json.dumps(CONFIG));cfg['limits']['wall_clock_s']=.01
            r=V.run_agent(Slow(None),cfg,Path(tmp),'skill','B',V.Budget(2),lambda:None)
            self.assertEqual(r['stop_reason'],'limit_wall_clock')
            self.assertEqual(r['model_requests'],1)
            self.assertEqual(r['tool_calls'],0)

class ArchiveTests(unittest.TestCase):
    def test_deleted_output_directory_still_has_a_recordable_final_result(self):
        import run_v5
        with tempfile.TemporaryDirectory() as tmp:
            ws=T.build_workspace('events','E1','L3',44,Path(tmp)/'ws')
            before=run_v5.env_hash(ws)
            (ws/'output').rmdir()
            dest=Path(tmp)/'traces';dest.mkdir()
            out=run_v5.collect_final('events','E1',44,ws,dest,before)
            self.assertEqual(out['final']['label'],'missing_output')
            self.assertTrue((dest/'output').is_dir())

class SamplingTests(unittest.TestCase):
    def test_every_planned_cell_has_five_distinct_shared_input_instances(self):
        import run_v5
        plan=json.loads((Path(__file__).resolve().parents[1]/'configs/plan_v5_report.json').read_text())
        specs=run_v5.order_for(plan)
        self.assertEqual(len(specs),180)
        self.assertEqual(len(set(specs)),180)
        cells={}
        for task,env,loc,cond,rep,seed in specs:cells.setdefault((task,env,loc,cond),[]).append(seed)
        self.assertEqual(len(cells),36)
        for seeds in cells.values():
            self.assertEqual(sorted(seeds),[2026111001,2026111002,2026111003,2026111004,2026111005])

if __name__=='__main__':unittest.main()
