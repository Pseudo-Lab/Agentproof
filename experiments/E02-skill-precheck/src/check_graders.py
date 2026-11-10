"""Offline grader and manipulation check (no model/API calls).

Required before any paid run:
  - input files are byte-identical in E0 and E1; the evidence file differs
  - the contract is identical in E0 and E1; L2 points to the evidence file, L3 does not mention it
  - oracle solution passes in E0 and E1
  - literal skill application passes in E0 and fails in E1 (the manipulation is real)
  - corrupted outputs (row/edge deleted, duplicated, wrong value, wrong key/header) and missing output fail
Writes a JSON report to stdout and exits non-zero on any violation.
"""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as T


def tree_hash(d):
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob('*')):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def corruptions(task, ws):
    out = ws / T.OUTPUT_FILE[task]
    if task == 'graph':
        def drop(data): data['edges'].pop(); return data
        def dup(data): data['edges'].append(dict(data['edges'][0])); return data
        def val(data): data['nodes'][0]['text'] += '!'; return data
        def extra_key(data): data['edges'][0]['weight'] = 1; return data
        for name, fn in [('drop_edge', drop), ('duplicate_edge', dup), ('wrong_value', val), ('extra_key', extra_key)]:
            yield name, (lambda fn=fn: out.write_text(json.dumps(fn(json.loads(out.read_text())))))
    else:
        def rewrite(fn):
            rows = fn(list(csv.reader(out.open(newline=''))))
            with out.open('w', newline='') as f:
                csv.writer(f).writerows(rows)
        def drop(rows): return rows[:-1]
        def dup(rows): return rows + [rows[-1]]
        def val(rows): rows[1][-1] = str(int(float(rows[1][-1])) + 1); return rows
        def header(rows): rows[0] = [h.upper() for h in rows[0]]; return rows
        for name, fn in [('drop_row', drop), ('duplicate_row', dup), ('wrong_value', val), ('bad_header', header)]:
            yield name, (lambda fn=fn: rewrite(fn))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds', type=int, nargs='+', default=[20261020, 20261027])
    args = p.parse_args()
    report, violations = [], []

    def record(entry, ok):
        report.append(entry)
        if not ok:
            violations.append(entry)

    for seed in args.seeds:
        for task in T.TASKS:
            for loc in T.LOCS:
                with tempfile.TemporaryDirectory() as d:
                    w0 = T.build_workspace(task, 'E0', loc, seed, Path(d) / 'e0')
                    w1 = T.build_workspace(task, 'E1', loc, seed, Path(d) / 'e1')
                    same_input = tree_hash(w0 / 'input') == tree_hash(w1 / 'input')
                    same_contract = (w0 / 'target_contract.json').read_bytes() == (w1 / 'target_contract.json').read_bytes()
                    ev = T.EVIDENCE_PATH[task]
                    diff_evidence = (w0 / ev).read_bytes() != (w1 / ev).read_bytes()
                    pointed = ev in (w0 / 'target_contract.json').read_text()
                    for name, ok in [('inputs_identical_E0_E1', same_input), ('contract_identical_E0_E1', same_contract),
                                     ('evidence_differs_E0_E1', diff_evidence),
                                     ('pointer_matches_loc', pointed == (loc == 'L2'))]:
                        record({'seed': seed, 'task': task, 'loc': loc, 'case': name, 'pass': ok}, ok)
                for env in T.ENVS:
                    for mode, want in [('oracle', True), ('literal', env == 'E0')]:
                        with tempfile.TemporaryDirectory() as d:
                            ws = T.build_workspace(task, env, loc, seed, Path(d) / 'ws')
                            T.solve(task, env, ws, mode)
                            ok, reason = T.grade(task, env, seed, ws)
                            record({'seed': seed, 'task': task, 'env': env, 'loc': loc, 'case': mode,
                                    'pass': ok, 'reason': reason}, ok == want)
                    with tempfile.TemporaryDirectory() as d:
                        base = T.build_workspace(task, env, loc, seed, Path(d) / 'base')
                        T.solve(task, env, base, 'oracle')
                        for name in [n for n, _ in corruptions(task, base)]:
                            ws = Path(d) / name
                            shutil.copytree(base, ws)
                            dict(corruptions(task, ws))[name]()
                            ok, reason = T.grade(task, env, seed, ws)
                            record({'seed': seed, 'task': task, 'env': env, 'loc': loc, 'case': name,
                                    'pass': ok, 'reason': reason}, not ok)
                        ws = T.build_workspace(task, env, loc, seed, Path(d) / 'empty')
                        ok, reason = T.grade(task, env, seed, ws)
                        record({'seed': seed, 'task': task, 'env': env, 'loc': loc, 'case': 'no_output',
                                'pass': ok, 'reason': reason}, not ok)
    print(json.dumps({'checks': len(report), 'violations': violations, 'results': report}, ensure_ascii=False, indent=1))
    sys.exit(1 if violations else 0)


if __name__ == '__main__':
    main()
