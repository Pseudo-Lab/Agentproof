"""Single-agent loop for E02 with four tools and a one-shot pre-application check hook.

Conditions
  A: read_skill returns "no skill" (reference)
  B: read_skill returns the fixed skill (baseline)
  C: same as B, plus HOOK_MESSAGE inserted once right after the read_skill output (intervention)
  C2: same as C with HOOK_MESSAGE_LOC (names kinds of places to check) (v3 comparison arm)

The first model request is forced to call read_skill in every condition.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOK_MESSAGE = (
    '방금 제공된 절차를 적용하기 전에, 결과에 영향을 주는 전제 1~2개를 현재 과제·입력 파일·환경의 근거와 '
    '대조하세요. 필요한 근거를 확인하고, 맞는 부분은 사용하되 맞지 않는 부분은 수정하거나 사용하지 마세요. '
    '확인 비용도 전체 실행 예산에 포함됩니다.'
)
# C2 (v3, pre-registered before any v3 run): same slot and similar length as C, but names the
# kinds of places to check. It never names a specific file, field, value or answer.
HOOK_MESSAGE_LOC = (
    '방금 제공된 절차를 적용하기 전에, 결과에 영향을 주는 전제 1~2개를 입력 파일뿐 아니라 작업 공간에서 '
    '이 결과를 읽거나 규정하는 파일(소비자 코드, 설정, 출처 메타데이터 등)과 대조하세요. 작업 공간의 파일 '
    '목록부터 확인하고, 맞는 부분은 사용하되 맞지 않는 부분은 수정하거나 사용하지 마세요. '
    '확인 비용도 전체 실행 예산에 포함됩니다.'
)
HOOKS = {'C': HOOK_MESSAGE, 'C2': HOOK_MESSAGE_LOC}
SYSTEM_PROMPT = (
    '당신은 파일 작업 에이전트입니다. 주어진 도구만 사용해 작업 공간에서 과제를 수행하세요. '
    '파일 경로는 작업 공간 기준 상대 경로를 씁니다. run_python은 Python 표준 라이브러리만 사용할 수 있습니다.'
)
NO_SKILL = '이 과제에 제공된 스킬이 없습니다.'

TOOLS = [
    {'type': 'function', 'name': 'read_skill', 'strict': True,
     'description': '이 과제에 제공된 스킬(작업 절차서)의 내용을 읽는다.',
     'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}},
    {'type': 'function', 'name': 'read_file', 'strict': True,
     'description': '작업 공간의 텍스트 파일을 읽는다.',
     'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'description': '작업 공간 기준 상대 경로'}},
                    'required': ['path'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'write_file', 'strict': True,
     'description': 'output/ 아래에 텍스트 파일을 쓴다(덮어쓰기).',
     'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                    'required': ['path', 'content'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'run_python', 'strict': True,
     'description': '작업 공간을 현재 디렉터리로 Python 코드를 실행하고 stdout/stderr를 돌려준다. 30초 제한.',
     'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}},
                    'required': ['code'], 'additionalProperties': False}},
]

READ_LIMIT = 20_000
PY_OUTPUT_LIMIT = 6_000
PY_TIMEOUT_S = 30
LEAK_MARKERS = ('E02-skill-precheck', 'agentproof', 'check_graders', 'tasks.py')


class Limits:
    def __init__(self, cfg):
        self.max_requests = cfg['max_model_requests']
        self.max_tool_calls = cfg['max_tool_calls']
        self.wall_s = cfg['wall_clock_s']
        self.max_input = cfg['max_cumulative_input_tokens']
        self.max_output = cfg['max_cumulative_output_tokens']


def _inside(ws, rel):
    p = (ws / rel).resolve()
    return p if p == ws or ws in p.parents else None


def execute_tool(name, args, ws, skill_text):
    ws = ws.resolve()
    if name == 'read_skill':
        return skill_text if skill_text is not None else NO_SKILL
    if name == 'read_file':
        p = _inside(ws, args.get('path', ''))
        if p is None:
            return 'ERROR: 작업 공간 밖의 경로는 읽을 수 없습니다.'
        if not p.is_file():
            listing = sorted(str(q.relative_to(ws)) for q in ws.rglob('*') if q.is_file())
            return 'ERROR: 파일이 없습니다. 작업 공간 파일: ' + ', '.join(listing)
        text = p.read_text(errors='replace')
        return text if len(text) <= READ_LIMIT else text[:READ_LIMIT] + f'\n...[truncated {len(text) - READ_LIMIT} chars]'
    if name == 'write_file':
        p = _inside(ws, args.get('path', ''))
        if p is None or (ws / 'output') not in [p, *p.parents] or p == ws / 'output':
            return 'ERROR: output/ 아래 파일에만 쓸 수 있습니다.'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args.get('content', ''))
        return f'OK: {p.relative_to(ws)} ({len(args.get("content", ""))} chars)'
    if name == 'run_python':
        env = {'PATH': '/usr/bin:/bin:/usr/local/bin', 'HOME': str(ws), 'TZ': 'UTC', 'LANG': 'C.UTF-8',
               'PYTHONHASHSEED': '0'}  # no API keys or user env reach the sandboxed code
        try:
            proc = subprocess.run([sys.executable, '-I', '-c', args.get('code', '')], cwd=ws, env=env,
                                  capture_output=True, text=True, timeout=PY_TIMEOUT_S)
            out = f'exit={proc.returncode}\n--- stdout\n{proc.stdout}\n--- stderr\n{proc.stderr}'
        except subprocess.TimeoutExpired:
            out = f'ERROR: {PY_TIMEOUT_S}초 시간 초과'
        return out if len(out) <= PY_OUTPUT_LIMIT else out[:PY_OUTPUT_LIMIT] + '\n...[truncated]'
    return f'ERROR: 알 수 없는 도구 {name}'


def _dump(item):
    d = item.model_dump(exclude_none=True) if hasattr(item, 'model_dump') else dict(item)
    return d


def _trace_view(item):
    """Copy of an input item for the trace file, without encrypted reasoning blobs."""
    d = dict(item)
    if d.get('type') == 'reasoning':
        d.pop('encrypted_content', None)
    return d


def run_agent(client, model_cfg, limits, task_prompt, ws, skill_text, condition, budget):
    """Run one trial. Returns a dict with usage, counts, stop reason and trace. Never raises on API errors."""
    ws = Path(ws)
    items = [{'role': 'user', 'content': task_prompt}]
    usage = {'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens': 0, 'cached_input_tokens': 0}
    n_req = n_tool = hook_count = 0
    stop, error, final_text, response_ids, leak_flags = None, None, None, [], []
    started = time.monotonic()
    last_input = 0
    while True:
        if n_req >= limits.max_requests:
            stop = 'limit_model_requests'; break
        if time.monotonic() - started > limits.wall_s:
            stop = 'limit_wall_clock'; break
        remaining_out = limits.max_output - usage['output_tokens']
        if remaining_out < 256:
            stop = 'limit_output_tokens'; break
        est_next_input = last_input + sum(len(json.dumps(i, ensure_ascii=False)) for i in items[-6:]) // 2
        if usage['input_tokens'] + est_next_input > limits.max_input:
            stop = 'limit_input_tokens'; break
        worst = (min(est_next_input * 2, limits.max_input) * model_cfg['price_input_per_mtok'] +
                 remaining_out * model_cfg['price_output_per_mtok']) / 1e6
        if not budget.can_spend(worst):
            stop = 'budget_cap'; break
        kwargs = dict(model=model_cfg['model'], instructions=SYSTEM_PROMPT, input=items, tools=TOOLS,
                      reasoning={'effort': model_cfg['reasoning_effort']}, store=False,
                      include=['reasoning.encrypted_content'], parallel_tool_calls=False,
                      max_output_tokens=remaining_out)
        if n_req == 0:
            kwargs['tool_choice'] = {'type': 'function', 'name': 'read_skill'}
        try:
            resp = client.responses.create(**kwargs)
        except Exception as exc:  # infra/API failure: recorded, not retried
            error = f'{type(exc).__name__}: {str(exc)[:300]}'
            stop = 'api_error'; break
        n_req += 1
        response_ids.append(getattr(resp, 'id', None))
        u = resp.usage
        last_input = u.input_tokens
        usage['input_tokens'] += u.input_tokens
        usage['output_tokens'] += u.output_tokens
        det_out = getattr(u, 'output_tokens_details', None)
        det_in = getattr(u, 'input_tokens_details', None)
        usage['reasoning_tokens'] += (getattr(det_out, 'reasoning_tokens', 0) or 0) if det_out else 0
        usage['cached_input_tokens'] += (getattr(det_in, 'cached_tokens', 0) or 0) if det_in else 0
        budget.spend((u.input_tokens * model_cfg['price_input_per_mtok'] +
                      u.output_tokens * model_cfg['price_output_per_mtok']) / 1e6)
        out_items = [_dump(i) for i in resp.output]
        items.extend(out_items)
        if getattr(resp, 'status', 'completed') == 'incomplete':
            stop = 'limit_output_tokens'; break
        calls = [i for i in out_items if i.get('type') == 'function_call']
        if not calls:
            final_text = getattr(resp, 'output_text', None)
            stop = 'agent_finished'; break
        for call in calls:
            if n_tool >= limits.max_tool_calls:
                stop = 'limit_tool_calls'; break
            n_tool += 1
            try:
                args = json.loads(call.get('arguments') or '{}')
            except json.JSONDecodeError:
                args = {}
            if any(m in json.dumps(args) for m in LEAK_MARKERS):
                leak_flags.append(call.get('name'))
            result = execute_tool(call['name'], args, ws, skill_text)
            items.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': result})
            if call['name'] == 'read_skill' and condition in HOOKS and hook_count == 0:
                items.append({'role': 'developer', 'content': HOOKS[condition]})
                hook_count += 1
        if stop:
            break
    return {'usage': usage, 'model_requests': n_req, 'tool_calls': n_tool, 'hook_count': hook_count,
            'stop_reason': stop, 'error': error, 'final_text': final_text, 'response_ids': response_ids,
            'elapsed_s': time.monotonic() - started, 'leak_flags': leak_flags,
            'trace': [_trace_view(i) for i in items]}


# ------------------------------------------------------------------ offline mock client
class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self, exclude_none=True):
        def conv(v):
            if isinstance(v, _Obj):
                return v.model_dump(exclude_none)
            if isinstance(v, list):
                return [conv(x) for x in v]
            return v
        return {k: conv(v) for k, v in self.__dict__.items() if not (exclude_none and v is None)}


class MockClient:
    """Scripted stand-in for the Responses API. Exercises plumbing only; not evidence of anything.
    Policy: read_skill -> (C and saw hook: contract-following answer | otherwise: literal skill answer) -> finish."""

    def __init__(self, solve_fn):
        self.solve_fn = solve_fn  # solve_fn(mode) -> (relative_path, content)
        self.responses = self
        self._n = 0

    def create(self, **kw):
        items = kw['input']
        n_calls = sum(1 for i in items if i.get('type') == 'function_call')
        saw_hook = any(i.get('role') == 'developer' for i in items)
        usage = _Obj(input_tokens=1200 + 400 * n_calls, output_tokens=150,
                     output_tokens_details=_Obj(reasoning_tokens=64), input_tokens_details=_Obj(cached_tokens=0))
        self._n += 1
        if n_calls == 0:
            assert kw.get('tool_choice', {}).get('name') == 'read_skill'
            out = [_Obj(type='function_call', call_id=f'c{self._n}', name='read_skill', arguments='{}')]
        elif n_calls == 1:
            path, content = self.solve_fn('oracle' if saw_hook else 'literal')
            out = [_Obj(type='function_call', call_id=f'c{self._n}', name='write_file',
                        arguments=json.dumps({'path': path, 'content': content}))]
        else:
            return _Obj(id=f'mock-{self._n}', output=[_Obj(type='message', role='assistant',
                        content=[_Obj(type='output_text', text='완료했습니다.')])], usage=usage,
                        status='completed', output_text='완료했습니다.')
        return _Obj(id=f'mock-{self._n}', output=out, usage=usage, status='completed', output_text='')
