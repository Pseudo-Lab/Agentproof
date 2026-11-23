"""Agent loop for E02 v4 (SkillsBench tasks in Docker).

Tools: read_skill, read_file, write_file, run_shell (all inside the task container).
Conditions
  A   no skill (read_skill returns "no skill")
  B   skill only                                   (baseline)
  C   B + generic pre-application check, once right after the read_skill output
  C2  B + premise-targeted pre-application check, same slot
  P   C2 + one post-check right before the agent finishes (first final answer is withheld once)
  S   skill with an appended applicability/risk section (skill-side, BASM-style), no harness message
The first model request is forced to call read_skill in every condition.
"""
import json
import time

HOOK_C = (
    '방금 제공된 절차를 적용하기 전에, 결과에 영향을 주는 전제 1~2개를 현재 과제·입력 파일·환경의 근거와 '
    '대조하세요. 필요한 근거를 확인하고, 맞는 부분은 사용하되 맞지 않는 부분은 수정하거나 사용하지 마세요. '
    '확인 비용도 전체 실행 예산에 포함됩니다.'
)
HOOK_C2 = (
    '방금 제공된 절차를 적용하기 전에, 절차에 적힌 구체적인 값(단위, 변환 계수, 버전, 파라미터, 형식, 키 이름 등) 중 '
    '결과에 영향을 주는 것 1~2개를 골라, 과제 지시문과 작업 공간의 데이터·참고 문서·코드에서 그 값을 뒷받침하는 '
    '근거를 찾아 대조하세요. 근거와 다르면 절차의 값을 쓰지 말고 근거를 따르세요. 확인 비용도 전체 실행 예산에 포함됩니다.'
)
HOOK_POST = (
    '완료하기 전에, 결과물에 쓰인 핵심 값(단위, 계수, 버전, 파라미터, 형식, 키 이름 등)이 과제 지시문과 작업 공간의 '
    '근거와 맞는지 실제로 확인하세요. 다르면 결과물을 고친 뒤 완료하고, 맞으면 그대로 완료하세요.'
)
PRE_HOOKS = {'C': HOOK_C, 'C2': HOOK_C2, 'P': HOOK_C2}
SYSTEM_PROMPT = (
    '당신은 리눅스 컨테이너 안에서 작업하는 에이전트입니다. 주어진 도구만 사용해 과제를 끝까지 수행하세요. '
    '경로는 절대 경로를 권장합니다. 네트워크는 사용할 수 없습니다. 과제를 마치면 도구를 더 호출하지 말고 '
    '한두 문장으로 완료를 알리세요.'
)
NO_SKILL = '이 과제에 제공된 스킬이 없습니다.'
READ_LIMIT = 20_000
SHELL_OUT_LIMIT = 8_000
SHELL_TIMEOUT_S = 120

TOOLS = [
    {'type': 'function', 'name': 'read_skill', 'strict': True,
     'description': '이 과제에 제공된 스킬(작업 절차서)의 SKILL.md 내용과 스킬 폴더의 파일 경로를 읽는다.',
     'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}},
    {'type': 'function', 'name': 'read_file', 'strict': True,
     'description': '컨테이너 안의 텍스트 파일을 읽는다(최대 20,000자).',
     'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}},
                    'required': ['path'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'write_file', 'strict': True,
     'description': '컨테이너 안에 텍스트 파일을 쓴다(덮어쓰기, 상위 폴더 자동 생성).',
     'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                    'required': ['path', 'content'], 'additionalProperties': False}},
    {'type': 'function', 'name': 'run_shell', 'strict': True,
     'description': '컨테이너 안에서 bash 명령을 실행하고 exit code, stdout, stderr를 돌려준다. 120초 제한.',
     'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}},
                    'required': ['command'], 'additionalProperties': False}},
]

FORBIDDEN = ('/verifier', '/oracle', '/logs/verifier')


class Limits:
    def __init__(self, cfg):
        self.max_requests = cfg['max_model_requests']
        self.max_tool_calls = cfg['max_tool_calls']
        self.wall_s = cfg['wall_clock_s']
        self.max_input = cfg['max_cumulative_input_tokens']
        self.max_output = cfg['max_cumulative_output_tokens']


def make_executor(container, skill_text):
    def execute(name, args):
        if name == 'read_skill':
            return skill_text if skill_text is not None else NO_SKILL
        if name == 'read_file':
            path = args.get('path', '')
            rc, out, err = container.exec(f'head -c {READ_LIMIT + 1} -- {json.dumps(path)}', timeout=30)
            if rc != 0:
                return f'ERROR: {err.strip()[:500]}'
            return out if len(out) <= READ_LIMIT else out[:READ_LIMIT] + '\n...[truncated]'
        if name == 'write_file':
            path, content = args.get('path', ''), args.get('content', '')
            p = json.dumps(path)
            rc, out, err = container.exec(f'mkdir -p "$(dirname {p})" && cat > {p}', timeout=30, stdin=content)
            return f'OK: {path} ({len(content)} chars)' if rc == 0 else f'ERROR: {err.strip()[:500]}'
        if name == 'run_shell':
            rc, out, err = container.exec(args.get('command', ''), timeout=SHELL_TIMEOUT_S)
            res = f'exit={rc}\n--- stdout\n{out}\n--- stderr\n{err}'
            return res if len(res) <= SHELL_OUT_LIMIT else res[:SHELL_OUT_LIMIT // 2] + '\n...[truncated]...\n' + res[-SHELL_OUT_LIMIT // 2:]
        return f'ERROR: 알 수 없는 도구 {name}'
    return execute


def _trace_view(item):
    d = dict(item)
    if d.get('type') == 'reasoning':
        d.pop('encrypted_content', None)
    return d


def run_agent(client, model_cfg, limits, task_prompt, execute, condition, budget):
    items = [{'role': 'user', 'content': task_prompt}]
    usage = {'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens': 0, 'cached_input_tokens': 0}
    n_req = n_tool = pre_hooks = post_hooks = 0
    stop, error, final_text, response_ids, forbidden_hits = None, None, None, [], 0
    started = time.monotonic()
    last_input = 0
    while True:
        if n_req >= limits.max_requests:
            stop = 'limit_model_requests'; break
        if time.monotonic() - started > limits.wall_s:
            stop = 'limit_wall_clock'; break
        remaining_out = limits.max_output - usage['output_tokens']
        if remaining_out < 512:
            stop = 'limit_output_tokens'; break
        est_next = last_input + sum(len(json.dumps(i, ensure_ascii=False)) for i in items[-6:]) // 2
        if usage['input_tokens'] + est_next > limits.max_input:
            stop = 'limit_input_tokens'; break
        worst = (min(est_next * 2, limits.max_input) * model_cfg['price_input_per_mtok'] +
                 min(remaining_out, 8000) * model_cfg['price_output_per_mtok']) / 1e6
        if not budget.can_spend(worst):
            stop = 'budget_cap'; break
        kwargs = dict(model=model_cfg['model'], instructions=SYSTEM_PROMPT, input=items, tools=TOOLS,
                      reasoning={'effort': model_cfg['reasoning_effort']}, store=False,
                      include=['reasoning.encrypted_content'], parallel_tool_calls=False,
                      max_output_tokens=min(remaining_out, 16000))
        if n_req == 0:
            kwargs['tool_choice'] = {'type': 'function', 'name': 'read_skill'}
        try:
            resp = client.responses.create(**kwargs)
        except Exception as exc:
            error = f'{type(exc).__name__}: {str(exc)[:300]}'
            stop = 'api_error'; break
        n_req += 1
        response_ids.append(getattr(resp, 'id', None))
        u = resp.usage
        last_input = u.input_tokens
        usage['input_tokens'] += u.input_tokens
        usage['output_tokens'] += u.output_tokens
        det_out, det_in = getattr(u, 'output_tokens_details', None), getattr(u, 'input_tokens_details', None)
        usage['reasoning_tokens'] += (getattr(det_out, 'reasoning_tokens', 0) or 0) if det_out else 0
        usage['cached_input_tokens'] += (getattr(det_in, 'cached_tokens', 0) or 0) if det_in else 0
        budget.spend((u.input_tokens * model_cfg['price_input_per_mtok'] +
                      u.output_tokens * model_cfg['price_output_per_mtok']) / 1e6)
        out_items = [dict(i) for i in resp.output]
        items.extend(out_items)
        if getattr(resp, 'status', 'completed') == 'incomplete':
            stop = 'limit_output_tokens'; break
        calls = [i for i in out_items if i.get('type') == 'function_call']
        if not calls:
            if condition == 'P' and post_hooks == 0:
                items.append({'role': 'developer', 'content': HOOK_POST})
                post_hooks += 1
                continue
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
            if any(f in json.dumps(args) for f in FORBIDDEN):
                forbidden_hits += 1
            result = execute(call['name'], args)
            items.append({'type': 'function_call_output', 'call_id': call['call_id'], 'output': result})
            if call['name'] == 'read_skill' and condition in PRE_HOOKS and pre_hooks == 0:
                items.append({'role': 'developer', 'content': PRE_HOOKS[condition]})
                pre_hooks += 1
        if stop:
            break
    return {'usage': usage, 'model_requests': n_req, 'tool_calls': n_tool, 'pre_hooks': pre_hooks,
            'post_hooks': post_hooks, 'stop_reason': stop, 'error': error, 'final_text': final_text,
            'response_ids': response_ids, 'elapsed_s': time.monotonic() - started,
            'forbidden_hits': forbidden_hits, 'trace': [_trace_view(i) for i in items]}
