"""Manipulation check for E02 v4 (no model calls).

For each task in sb/tasks.json:
  1. build the image from the pinned SkillsBench task
  2. oracle (original solve.sh, original skills)             -> verifier reward must be 1.0
  3. literal-E1 oracle (solve.sh with the E1 premise applied) -> reward must be < 1.0
  4. E1 skill edits and S sections apply cleanly; skill length change within ±5%
Writes results/sb/checks/<run-id>.json.

  python3 sb/check_sb.py --sb-root ~/Documents/ChatGPT/Agentproof/skillsbench --run-id check-001 [--tasks a b]
"""
import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C
import docker_env as D


def oracle_run(task_dir, tag, meta, oracle_dir, skills_dir):
    c = D.Container(tag, D.workdir_of(tag, meta), meta.get('sandbox.cpus', 2), meta.get('sandbox.memory_mb', 4096),
                    offline=False)  # oracle may install packages
    try:
        for root in ('/root/.claude/skills', '/root/environment/skills', '/app/skills', '/skills'):
            c.put_dir(skills_dir, root)
        c.put_dir(oracle_dir, '/oracle')
        rc, out, err = c.exec('bash /oracle/solve.sh', timeout=int(meta.get('agent.timeout_sec', 900)))
        res = c.run_verifier(Path(task_dir) / 'verifier', timeout=int(min(meta.get('verifier.timeout_sec', 900), 1200)))
        res['oracle_exit'] = rc
        res['oracle_tail'] = (out + err)[-1500:]
        return res
    finally:
        c.remove()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--sb-root', required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--tasks', nargs='*')
    args = p.parse_args()
    cfg = C.load_tasks_config()
    out_dir = C.EXPERIMENT / 'results' / 'sb' / 'checks'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{args.run_id}.json'
    if out.exists():
        p.error('run-id exists')
    report = {'run_id': args.run_id, 'sb_commit': cfg['sb_commit'],
              'started_at_utc': datetime.now(timezone.utc).isoformat(), 'tasks': {}}
    for t in cfg['tasks']:
        name = t['name']
        if args.tasks and name not in args.tasks:
            continue
        task_dir = args.sb_root / 'tasks' / name
        r = {}
        try:
            meta, _ = D.parse_task_md(task_dir / 'task.md')
            tag = D.build_image(task_dir, name, cfg['sb_commit'])
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                orig = tmp / 'skills_e0'
                shutil.copytree(task_dir / 'environment' / 'skills', orig)
                e1 = tmp / 'skills_e1'
                shutil.copytree(orig, e1)
                C.apply_edits(e1, t['skill_edits_E1'])
                len0, len1 = (sum(len(f.read_text(errors='ignore')) for f in d.rglob('*.md')) for d in (orig, e1))
                r['skill_len_change_pct'] = round(100 * (len1 - len0) / len0, 2)
                for env in ('E0', 'E1'):
                    s = tmp / f's_{env}'
                    C.materialize_skills(task_dir, t, env, 'S', s)
                r['oracle'] = oracle_run(task_dir, tag, meta, task_dir / 'oracle', orig)
                lit = tmp / 'oracle_literal'
                shutil.copytree(task_dir / 'oracle', lit)
                C.apply_edits(lit, t['literal_oracle_edits_E1'])
                r['literal_E1'] = oracle_run(task_dir, tag, meta, lit, orig)
            r['pass'] = (r['oracle']['reward'] == 1.0 and (r['literal_E1']['reward'] or 0) < 1.0
                         and abs(r['skill_len_change_pct']) <= 5)
        except Exception as exc:  # record and continue with the next task
            r['error'] = f'{type(exc).__name__}: {str(exc)[:600]}'
            r['pass'] = False
        report['tasks'][name] = r
        print(f"{name:40s} pass={r['pass']} oracle={r.get('oracle', {}).get('reward')} "
              f"literal_E1={r.get('literal_E1', {}).get('reward')} len%={r.get('skill_len_change_pct')} "
              f"{r.get('error', '')[:120]}", flush=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
