"""Versioned v5 policies and observable output diagnostics; no API calls on import."""
import json
import threading
import time
from pathlib import Path
import agent as A
import tasks as T

AUTHORITY = ('target_contract.json은 기본 요구사항이며, 작업 공간에 제공된 현재 환경 근거가 입력 해석과 출력 세부사항을 정합니다. '
             '스킬은 일반 절차이므로 현재 환경 근거와 충돌하면 현재 근거를 우선합니다. '
             '필요한 확인을 마친 뒤 결과를 작성하고 완료를 알리세요.')
TASK_PROMPT = ('작업 공간의 input/ 폴더를 처리해 output/ 폴더에 결과를 작성하세요. '
               '제공된 절차서는 read_skill로 먼저 확인하세요. ' + AUTHORITY)
PRE = ('방금 읽은 절차에서 결과를 좌우하는 구체적인 전제 1~2개를 골라 현재 작업의 근거와 대조하세요. '
       '작업 공간의 파일 목록부터 확인한 뒤 근거를 찾아보세요. 근거와 어긋나면 절차를 수정해서 적용하세요. '
       '확인 비용은 같은 실행 한도에 포함됩니다.')
POST = ('완료하기 전에 결과물의 핵심 값이 현재 작업의 명세와 근거에 맞는지 실제로 확인하세요. '
        '다르면 결과물을 수정한 뒤 완료하고, 맞으면 그대로 완료하세요. 같은 실행 한도 안에서 수행하세요.')
NEUTRAL_PRE = '이어서 작업을 진행하세요.'
NEUTRAL_POST = '작업을 마쳤다면 완료를 알리세요.'
POLICIES = {'B': (None, None), 'N': (NEUTRAL_PRE, NEUTRAL_POST),
            'C2': (PRE, NEUTRAL_POST), 'V': (NEUTRAL_PRE, POST), 'P': (PRE, POST)}


class Budget:
    """Atomic reservations. Unknown billing consumes its upper-bound reservation."""
    def __init__(self, cap):
        self.cap=float(cap);self.spent=0.;self.reserved={};self.lock=threading.Lock();self.next_id=0
        self.unknown_cost=0.

    def reserve(self, worst):
        with self.lock:
            if worst < 0 or self.spent+sum(self.reserved.values())+worst > self.cap+1e-12:
                return None
            self.next_id+=1;self.reserved[self.next_id]=worst
            return self.next_id

    def settle(self, ticket, actual):
        with self.lock:
            worst=self.reserved.pop(ticket)
            self.spent+=actual
            if actual > worst+1e-9:
                raise RuntimeError('usage exceeded reserved upper bound')

    def unknown(self, ticket):
        with self.lock:
            worst=self.reserved.pop(ticket);self.spent+=worst;self.unknown_cost+=worst


def diagnose(task, env, seed, ws):
    if not (Path(ws)/T.OUTPUT_FILE[task]).is_file():
        return dict(label='missing_output',target_pass=False,other_pass=False,reason='missing_output')
    diagnostic_errors=[]
    try:target,reason=T.grade(task,env,seed,ws)
    except (TypeError,ValueError,KeyError,IndexError,OverflowError) as exc:
        target=False;reason='invalid_output_structure'
        diagnostic_errors.append(f'target: {type(exc).__name__}: {str(exc)[:120]}')
    try:other,_=T.grade(task,'E0' if env=='E1' else 'E1',seed,ws)
    except (TypeError,ValueError,KeyError,IndexError,OverflowError) as exc:
        other=False
        diagnostic_errors.append(f'other: {type(exc).__name__}: {str(exc)[:120]}')
    label='correct' if target else ('skill_consistent_mismatch' if env=='E1' and other else 'other_error')
    return dict(label=label,target_pass=target,other_pass=other,reason=reason,diagnostic_errors=diagnostic_errors)


def run_agent(client, cfg, ws, skill, condition, budget, snapshot):
    pre,post=POLICIES[condition];lim=A.Limits(cfg['limits'])
    items=[{'role':'user','content':TASK_PROMPT}]
    usage=dict(input_tokens=0,output_tokens=0,reasoning_tokens=0,cached_input_tokens=0)
    requests=tools=pre_count=post_count=0
    before_post=None;stop=error=final_text=None;ids=[];leaks=[];reads=[]
    started=time.monotonic();unknown_cost=0.
    while True:
        if requests>=lim.max_requests:stop='limit_model_requests';break
        if time.monotonic()-started>lim.wall_s:stop='limit_wall_clock';break
        remaining=lim.max_output-usage['output_tokens']
        if remaining<256:stop='limit_output_tokens';break
        per_output=min(4096,remaining)
        kw=dict(model=cfg['model'],instructions=A.SYSTEM_PROMPT,input=items,tools=A.TOOLS,
                reasoning={'effort':cfg['reasoning_effort']},store=False,
                include=['reasoning.encrypted_content'],parallel_tool_calls=False,max_output_tokens=per_output)
        if requests==0:kw['tool_choice']={'type':'function','name':'read_skill'}
        # UTF-8 bytes + generous structural overhead bounds this short text/tool-only payload.
        # Reserve the entire allowed cumulative input budget for one request, not an optimistic estimate.
        byte_bound=len(json.dumps(kw,ensure_ascii=False).encode('utf8'))+8192
        if byte_bound+usage['input_tokens']>lim.max_input:stop='limit_input_tokens';break
        worst=(lim.max_input*cfg['price_input_per_mtok']+per_output*cfg['price_output_per_mtok'])/1e6
        ticket=budget.reserve(worst)
        if ticket is None:stop='budget_cap';break
        if hasattr(client,'timeout_s'):
            client.timeout_s=max(.001,min(client.timeout_s,lim.wall_s-(time.monotonic()-started)))
        try:response=client.responses.create(**kw)
        except Exception as exc:
            budget.unknown(ticket);unknown_cost+=worst
            stop='api_error';error=f'{type(exc).__name__}: {str(exc)[:250]}';break
        u=response.usage
        actual=(u.input_tokens*cfg['price_input_per_mtok']+u.output_tokens*cfg['price_output_per_mtok'])/1e6
        budget.settle(ticket,actual)
        requests+=1;ids.append(getattr(response,'id',None))
        usage['input_tokens']+=u.input_tokens;usage['output_tokens']+=u.output_tokens
        for field,details,token in [('reasoning_tokens','output_tokens_details','reasoning_tokens'),
                                    ('cached_input_tokens','input_tokens_details','cached_tokens')]:
            usage[field]+=getattr(getattr(u,details,None),token,0) or 0
        out=[A._dump(i) for i in response.output];items.extend(out)
        if time.monotonic()-started>lim.wall_s:stop='limit_wall_clock';break
        if getattr(response,'status','completed')!='completed':stop='limit_output_tokens';break
        calls=[i for i in out if i.get('type')=='function_call']
        if not calls:
            if not any(i.get('type')=='message' for i in out):stop='missing_final_message';break
            final_text=getattr(response,'output_text',None)
            if before_post is None:
                try:before_post=snapshot()
                except Exception as exc:
                    stop='snapshot_error';error=f'{type(exc).__name__}: {str(exc)[:200]}';break
            if post is not None and post_count==0:
                items.append({'role':'developer','content':post});post_count=1;continue
            stop='agent_finished';break
        for call in calls:
            if tools>=lim.max_tool_calls:stop='limit_tool_calls';break
            tools+=1
            try:args=json.loads(call.get('arguments') or '{}')
            except json.JSONDecodeError:args={}
            if any(m in json.dumps(args) for m in A.LEAK_MARKERS):leaks.append(call.get('name'))
            try:result=A.execute_tool(call['name'],args,ws,skill)
            except Exception as exc:result=f'ERROR: {type(exc).__name__}: {str(exc)[:200]}'
            if call['name']=='read_file':
                rel=args.get('path','')
                path=(Path(ws)/rel).resolve()
                reads.append(dict(path=rel,successful=path.is_file() and not result.startswith('ERROR:')))
            items.append(dict(type='function_call_output',call_id=call['call_id'],output=result))
            if time.monotonic()-started>lim.wall_s:stop='limit_wall_clock';break
            if call['name']=='read_skill' and pre is not None and pre_count==0:
                items.append({'role':'developer','content':pre});pre_count=1
        if stop:break
    return dict(usage=usage,model_requests=requests,tool_calls=tools,pre_hooks=pre_count,post_hooks=post_count,
                before_post=before_post,stop_reason=stop,error=error,final_text=final_text,response_ids=ids,
                elapsed_s=time.monotonic()-started,leak_flags=leaks,explicit_reads=reads,
                unknown_billing_upper_usd=unknown_cost,trace=[A._trace_view(i) for i in items])
