"""Task definitions for E02 (v3): workspace generation, contracts, graders and reference solutions.

Design factors per task
  env  E0: the skill's premise holds          E1: one premise differs
  loc  L2: the contract points to the evidence file
       L3: the evidence file exists in the workspace but nothing points to it
The input files are byte-identical in E0 and E1; only the evidence file differs.
The contract text depends on loc only (identical in E0 and E1).
Expected answers are recomputed from the seed at grading time; no answer file is written.
"""
import csv
import io
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

TASKS = ('graph', 'csv', 'events')
ENVS = ('E0', 'E1')
LOCS = ('L2', 'L3')
SEOUL = timezone(timedelta(hours=9))
EXPERIMENT = Path(__file__).resolve().parents[1]

OUTPUT_FILE = {'graph': 'output/graph.json', 'csv': 'output/normalized.csv', 'events': 'output/daily.csv'}
EVIDENCE_PATH = {'graph': 'consumer/importer.py', 'csv': 'meta/source.json', 'events': 'config/report.json'}
POINTER_RULE = '입력 해석과 출력 형식의 세부 사항은 {path}에 정해진 대로 따를 것'

TASK_PROMPT = (
    '작업 공간의 input/ 폴더에 있는 파일을 처리해서, target_contract.json에 적힌 요구사항대로 '
    '결과 파일을 output/ 폴더에 작성하세요. 이 작업에 쓸 수 있는 스킬(작업 절차서)이 제공될 수 있으니 '
    'read_skill로 확인하세요. 결과 파일을 다 쓰면 도구를 더 호출하지 말고 한 문장으로 완료를 알리세요.'
)


def _rng(seed, task):
    return random.Random(f'{seed}:{task}')


# ---------------------------------------------------------------- graph
def _graph_content(seed):
    rng = _rng(seed, 'graph')
    speakers = ['Guard', 'Traveler', 'Merchant']
    lines = ['Halt! Who goes there?', 'Just passing through.', 'State your business.',
             'I seek the old library.', 'The road is closed tonight.', 'Then I will wait.',
             'Safe travels.']
    nodes = [{'id': 'Start', 'text': lines[0], 'speaker': 'Guard', 'type': 'line'},
             {'id': 'Ask', 'text': '', 'speaker': '', 'type': 'choice'}]
    for i in range(1, 6):
        nodes.append({'id': f'L{i}', 'text': lines[i], 'speaker': rng.choice(speakers), 'type': 'line'})
    nodes.append({'id': 'End', 'text': lines[6], 'speaker': 'Guard', 'type': 'line'})
    edges = [('Start', 'Ask', ''), ('Ask', 'L1', '1. Just passing'), ('Ask', 'L2', '2. Stay silent'),
             ('Ask', 'L3', '3. Ask directions'), ('L1', 'L4', ''), ('L2', 'L4', ''), ('L3', 'L5', ''),
             ('L4', 'End', ''), ('L5', 'End', ''), ('L3', 'L4', ''), ('L2', 'L5', ''), ('L1', 'End', '')]
    rng.shuffle(edges)
    return nodes, edges


def _graph_keys(env):
    return ('from', 'to') if env == 'E0' else ('source', 'target')


# ---------------------------------------------------------------- csv
# Every raw value has the shape "d…d,ddd" (one comma, three digits after it), so the data alone
# cannot tell a decimal comma (E0: 12,345 -> 12.345) from a thousands separator (E1: 12,345 -> 12345).
def _csv_content(seed):
    rng = _rng(seed, 'csv')
    return [(f'M{i:03d}', rng.randint(1_000, 999_999)) for i in range(1, 41)]


def _csv_value(n, env):
    return f'{Decimal(n) / 1000:.3f}' if env == 'E0' else f'{n}.000'


# ---------------------------------------------------------------- events
def _events_content(seed):
    rng = _rng(seed, 'events')
    base = datetime(2026, 3, 2, tzinfo=timezone.utc)
    events = []
    for i in range(1, 61):
        day = rng.randint(0, 5)
        # at least a third of events fall in 15:00-23:59 UTC (next calendar day in Seoul)
        hour = rng.randint(15, 23) if i % 3 == 0 else rng.randint(0, 23)
        ts = base + timedelta(days=day, hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        events.append((f'E{i:03d}', ts, rng.randint(1, 100)))
    rng.shuffle(events)
    return events


# ---------------------------------------------------------------- contracts and evidence
def contract(task, loc):
    """Identical in E0 and E1. L2 adds one pointer rule to the evidence file; L3 has none."""
    if task == 'graph':
        c = {'output_file': OUTPUT_FILE[task],
             'format': {'nodes': [{'id': 'str', 'text': 'str', 'speaker': 'str', 'type': 'line | choice'}],
                        'edges': '간선 객체 목록 (출발 노드 id, 도착 노드 id, text)'},
             'rules': ['input/nodes.csv의 모든 노드와 input/edges.csv의 모든 간선을 정확히 한 번씩 포함',
                       '값은 입력 그대로 유지 (빈 text는 빈 문자열)']}
    elif task == 'csv':
        c = {'output_file': OUTPUT_FILE[task],
             'format': 'CSV 헤더 id,value. value는 천 단위 구분 기호 없이 소수점은 점, 소수 셋째 자리까지 (예: 7.250, 1234.500)',
             'rules': ['input/measurements.csv의 모든 행을 같은 순서로 유지', 'id는 입력 그대로',
                       '원래 측정값을 바꾸지 말 것']}
    elif task == 'events':
        c = {'output_file': OUTPUT_FILE[task],
             'format': 'CSV 헤더 date,count,sum. date는 YYYY-MM-DD 달력 날짜',
             'rules': ['input/events.csv의 ts_utc는 UTC 타임스탬프', '이벤트가 있는 날짜만, 날짜 오름차순',
                       'count는 이벤트 수, sum은 value 합계']}
    else:
        raise ValueError(task)
    if loc == 'L2':
        c['rules'].append(POINTER_RULE.format(path=EVIDENCE_PATH[task]))
    elif loc != 'L3':
        raise ValueError(loc)
    return c


def _evidence_text(task, env):
    if task == 'graph':
        src, dst = _graph_keys(env)
        return ('"""Dialogue engine importer. Reads output/graph.json as-is."""\n'
                'import json\n\n'
                f'EDGE_KEYS = {{"{src}", "{dst}", "text"}}\n\n\n'
                'def load(path="output/graph.json"):\n'
                '    with open(path) as f:\n'
                '        data = json.load(f)\n'
                '    nodes = {n["id"]: n for n in data["nodes"]}\n'
                '    edges = []\n'
                '    for e in data["edges"]:\n'
                '        if set(e) != EDGE_KEYS:\n'
                '            raise ValueError(f"unexpected edge keys: {sorted(e)}")\n'
                f'        edges.append((e["{src}"], e["{dst}"], e["text"]))\n'
                '    return nodes, edges\n')
    if task == 'csv':
        meta = ({'file': 'input/measurements.csv', 'source_system': 'LIMS-EU', 'locale': 'de-DE',
                 'decimal_separator': ',', 'thousands_separator': '.'} if env == 'E0' else
                {'file': 'input/measurements.csv', 'source_system': 'LIMS-US', 'locale': 'en-US',
                 'decimal_separator': '.', 'thousands_separator': ','})
        return json.dumps(meta, indent=2) + '\n'
    if task == 'events':
        return json.dumps({'report_name': 'daily-ops', 'report_timezone': 'UTC' if env == 'E0' else 'Asia/Seoul',
                           'week_start': 'monday', 'owner': 'ops-team'}, indent=2) + '\n'
    raise ValueError(task)


# ---------------------------------------------------------------- materialize
def build_workspace(task, env, loc, seed, dest):
    """Write task.md, target_contract.json, input/ and the evidence file into dest. No answers."""
    dest = Path(dest)
    (dest / 'input').mkdir(parents=True)
    (dest / 'output').mkdir()
    (dest / 'task.md').write_text(TASK_PROMPT + '\n')
    (dest / 'target_contract.json').write_text(json.dumps(contract(task, loc), ensure_ascii=False, indent=2) + '\n')
    if task == 'graph':
        nodes, edges = _graph_content(seed)
        with (dest / 'input/nodes.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['id', 'speaker', 'text', 'type'])
            for n in nodes:
                w.writerow([n['id'], n['speaker'], n['text'], n['type']])
        with (dest / 'input/edges.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['source', 'target', 'text'])
            w.writerows(edges)
    elif task == 'csv':
        with (dest / 'input/measurements.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['id', 'value'])
            for rid, n in _csv_content(seed):
                w.writerow([rid, f'{n:,}'])
    elif task == 'events':
        with (dest / 'input/events.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['event_id', 'ts_utc', 'value'])
            for eid, ts, value in _events_content(seed):
                w.writerow([eid, ts.strftime('%Y-%m-%dT%H:%M:%SZ'), value])
    ev = dest / EVIDENCE_PATH[task]
    ev.parent.mkdir(parents=True, exist_ok=True)
    ev.write_text(_evidence_text(task, env))
    return dest


def skill_path(task):
    return EXPERIMENT / 'skills' / task / 'SKILL.md'


# ---------------------------------------------------------------- expected answers
def expected(task, env, seed):
    if task == 'graph':
        nodes, edges = _graph_content(seed)
        src, dst = _graph_keys(env)
        return {'nodes': nodes, 'edges': [{src: s, dst: t, 'text': x} for s, t, x in edges]}
    if task == 'csv':
        return [(rid, _csv_value(n, env)) for rid, n in _csv_content(seed)]
    if task == 'events':
        tz = timezone.utc if env == 'E0' else SEOUL
        count, total = defaultdict(int), defaultdict(int)
        for _, ts, value in _events_content(seed):
            day = ts.astimezone(tz).strftime('%Y-%m-%d')
            count[day] += 1
            total[day] += value
        return [(d, str(count[d]), str(total[d])) for d in sorted(count)]
    raise ValueError(task)


def _other(env):
    return 'E1' if env == 'E0' else 'E0'


# ---------------------------------------------------------------- graders
def grade(task, env, seed, workspace):
    """Return (passed: bool, reason: str). Only a fully correct required output passes."""
    out = Path(workspace) / OUTPUT_FILE[task]
    if not out.is_file():
        return False, 'missing_output'
    want = expected(task, env, seed)
    try:
        text = out.read_text()
    except UnicodeDecodeError:
        return False, 'not_utf8'
    if task == 'graph':
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return False, 'invalid_json'
        if not isinstance(data, dict) or not isinstance(data.get('nodes'), list) or not isinstance(data.get('edges'), list):
            return False, 'bad_top_level_schema'
        def node_key(n):
            return tuple(sorted(n.items())) if isinstance(n, dict) else ('<invalid>',)
        if sorted(map(node_key, data['nodes'])) != sorted(map(node_key, want['nodes'])):
            return False, 'nodes_mismatch'
        src, dst = _graph_keys(env)
        for e in data['edges']:
            if not isinstance(e, dict) or set(e) != {src, dst, 'text'}:
                if isinstance(e, dict) and set(_graph_keys(_other(env))) <= set(e):
                    return False, 'premise_from_other_env'
                return False, 'edge_keys_wrong'
        got = sorted((e[src], e[dst], e['text']) for e in data['edges'])
        ref = sorted((e[src], e[dst], e['text']) for e in want['edges'])
        if len(got) != len(set(got)):
            return False, 'duplicate_edges'
        if got != ref:
            return False, 'edges_mismatch'
        return True, 'pass'
    rows = list(csv.reader(io.StringIO(text)))
    header = ['id', 'value'] if task == 'csv' else ['date', 'count', 'sum']
    if not rows or [h.strip() for h in rows[0]] != header:
        return False, 'bad_header'
    body = [tuple(c.strip() for c in r) for r in rows[1:] if any(c.strip() for c in r)]
    if body == want:
        return True, 'pass'
    if body == expected(task, _other(env), seed):
        return False, 'premise_from_other_env'
    if task == 'csv':
        if len(body) != len(want):
            return False, f'row_count_{len(body)}_vs_{len(want)}'
        if [r[0] for r in body] != [r[0] for r in want]:
            return False, 'ids_or_order_mismatch'
        return False, f'value_mismatch_{sum(r != w for r, w in zip(body, want))}_rows'
    if len(body) != len(want) or [r[0] for r in body] != [r[0] for r in want]:
        return False, 'date_set_mismatch'
    return False, 'count_or_sum_mismatch'


# ---------------------------------------------------------------- reference solutions (offline checks)
def solve(task, env, workspace, mode):
    """mode='oracle': uses the correct premise for env.
    mode='literal': applies the skill's premise (always the E0 premise) regardless of env."""
    ws = Path(workspace)
    use = env if mode == 'oracle' else 'E0'
    if task == 'graph':
        nodes = list(csv.DictReader((ws / 'input/nodes.csv').open(newline='')))
        edges = list(csv.DictReader((ws / 'input/edges.csv').open(newline='')))
        src, dst = _graph_keys(use)
        data = {'nodes': [{'id': n['id'], 'text': n['text'], 'speaker': n['speaker'], 'type': n['type']} for n in nodes],
                'edges': [{src: e['source'], dst: e['target'], 'text': e['text']} for e in edges]}
        (ws / OUTPUT_FILE[task]).write_text(json.dumps(data, indent=2))
    elif task == 'csv':
        rows = list(csv.DictReader((ws / 'input/measurements.csv').open(newline='')))
        with (ws / OUTPUT_FILE[task]).open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['id', 'value'])
            for r in rows:
                raw = r['value']
                if use == 'E0':  # skill parse_value: comma is the decimal separator
                    w.writerow([r['id'], f'{float(raw.replace(",", ".")):.3f}'])
                else:
                    w.writerow([r['id'], f'{Decimal(raw.replace(",", "")):.3f}'])
    elif task == 'events':
        tz = timezone.utc if use == 'E0' else SEOUL
        count, total = defaultdict(int), defaultdict(int)
        for r in csv.DictReader((ws / 'input/events.csv').open(newline='')):
            ts = datetime.strptime(r['ts_utc'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            day = ts.astimezone(tz).strftime('%Y-%m-%d')
            count[day] += 1
            total[day] += int(r['value'])
        with (ws / OUTPUT_FILE[task]).open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['date', 'count', 'sum'])
            for d in sorted(count):
                w.writerow([d, count[d], total[d]])
