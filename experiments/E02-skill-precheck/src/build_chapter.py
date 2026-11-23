"""Offline assembly of the E02 technical-report chapter from frozen run artifacts."""
import json
from pathlib import Path
from collections import Counter

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
P=EXP/'results/v5/report-v5-001'


def frac(rs):return f'{sum(r["status"]=="success" for r in rs)}/{len(rs)}'


def main():
    manifest=json.loads((P/'manifest.json').read_text())
    if not manifest.get('finished_at_utc'):
        raise SystemExit('Real v5 is still running; do not replace chapter with partial results.')
    rows=[json.loads(l) for l in (P/'trials.jsonl').read_text().splitlines()]
    a=json.loads((P/'analysis.json').read_text())
    supplement=json.loads((EXP/'analysis/v5_sensitivity.json').read_text())
    e=json.loads((EXP/'presentation/w6/evidence.json').read_text())
    source='[v5 protocol](../experiments/E02-skill-precheck/analysis/V5_PROTOCOL.md)'
    l=['# E02 · 스킬 적용 전 확인과 완료 전 검증의 효과', '',
       '장현서 · AgentProof 기술보고서 개별 연구 초안 · 2026-11-09', '',
       '## 요약', '',
       '이 연구는 스킬이 현재 환경과 어긋날 때 적용 전 확인이 과제 실패를 줄이는지, '
       '완료 전 검증이 어떤 종류의 오답을 수정하는지 살핀다. 사전 개입은 전제 대조와 작업 공간 목록 탐색을 묶은 정책이다. 기존 파일럿은 근거 탐색과 절차 적용의 실패를 드러냈지만, '
       '숨은 환경 파일의 권한을 명시하지 않았고 추가 실행 기회를 통제하지 못했다. '
       '이를 보완해 모든 조건에 환경 근거의 권한을 명시하고, 중립 메시지와 사전·사후 검증을 교차한 통제 실험을 추가했다. '
       '최종 성공과 반대 환경에 완전히 맞는 오답을 분리하고, 첫 완료 시도와 최종 산출물을 모두 기록했다.', '',
       f'새 실험은 실제 API로 **{len(rows)}/{manifest["planned_trials"]}회** 수행했다. '
       f'기록된 토큰 기준 비용은 **${manifest["known_cost_usd"]:.6f}**, '
       f'불명확한 청구를 포함한 보수적 예산 사용은 **${manifest["conservative_spent_usd"]:.6f}**다. '
       '세 개의 통제 과제군에 한정한 탐색 연구이며 공개 벤치마크 일반화를 확증하지 않는다.', '',
       '## 1. 문제와 선행연구', '',
       '스킬은 재사용 가능한 절차를 제공하지만, 그 전제가 현재 작업과 맞는지 별도로 판단해야 한다. '
       '[SkillsBench](https://arxiv.org/abs/2602.12670)는 공개 과제와 결정적 검증기를 제공한다. '
       '[SWE-Skills-Bench](https://arxiv.org/abs/2603.15401)는 일부 스킬이 지시를 덮어쓰는 문제를 보고한다. '
       '[Demystifying Agent Skills](https://arxiv.org/abs/2608.14036)는 절차적 앵커와 적용 실패를 분석한다. '
       '본 연구는 스킬 검색을 평가하지 않고, 이미 읽은 절차를 현재 작업에 적용하는 단계에 개입한다.', '',
       '연구 질문은 (a) 스킬 불일치가 피해를 만드는가, (b) 확인이 그 피해를 회복하는가, '
       '(c) 사후 검증이 일반 구현 오류를 줄이는 효과와 구분되는가로 나눈다. '
       '과제 실패와 스킬 오적용을 동일시하지 않는 것이 핵심이다.', '',
       '## 2. 기존 파일럿과 독립 재실행', '',
       '통제 과제 v3의 E1/L3는 근거 파일을 지시하지 않는 불일치 조건이다. 기존 확장 실행과 '
       '2026-11-09의 새 입력 seed 재실행은 다음과 같다. 두 실행을 합산하지 않았다.', '',
       '| 실행 | 과제 | 스킬만 B | 일반 확인 C | 위치 유형 안내 C2 |', '|---|---|---:|---:|---:|']
    for name in ('v3_original','v3_replication'):
        for task in ('graph','csv','events'):
            vals=[e['runs'][name]['cells'][f'{task}/E1/L3/{c}'] for c in ('B','C','C2')]
            l.append(f'| {name} | {task} | '+' | '.join(f'{v["success"]}/{v["n"]}' for v in vals)+' |')
    l+=['', '두 실행 모두 합계 B 0/15, C 0/15, C2 9/15였고, 과제별 C2도 5/5·4/5·0/5로 같았다. '
        '새 입력에서도 같은 패턴을 관찰했지만, 각 실행의 반복은 같은 입력을 재사용했고 과제군은 세 개뿐이다. '
        '과제 단위 차이의 기술적 부트스트랩 구간은 0~100%p다. 일반 확인의 보편적 무효나 C2의 일반적 유효성을 뜻하지 않는다.', '',
        '### 기존 L3 설계의 한계', '',
        '기존 지시문은 target_contract.json을 따르라고 하지만 L3에서는 언급되지 않은 환경 파일의 권한을 명시하지 않았다. '
        'CSV 표기와 보고 시간대는 입력만으로 확정할 수 없다. 따라서 기존 L3의 실패에는 요구사항의 미명시가 섞일 수 있다. '
        'C2의 파일 종류 안내가 탐색을 돕는 동시에 누락된 과제 맥락을 보충했을 가능성이 있다. '
        '이를 순수한 앵커링 효과라고 해석하지 않는다.', '',
        '### SkillsBench의 역할과 중단된 추가 실행', '',
        '기존 SkillsBench 216회에서 B는 E0 11/18, E1 13/18로 불일치의 행동상 피해가 확인되지 않았다. '
        'P−C2는 오류 제외 시 +27.5%p였지만, 오류를 포함하면 16/18 대 12/18, +22.2%p이며 '
        '과제 단위 구간은 −5.6~+50.0%p다. P−C2는 사전 등록된 부차 비교였으나, 후속 P 선택에는 이전 결과가 영향을 줬다.', '',
        '추가 SkillsBench 실행은 72회 계획 중 **33회 기록 후 중단**했다. 도구 timeout 후에도 컨테이너 내 Python '
        '프로세스가 살아남아 후속 호출과 verifier에 자원을 점유하는 것을 직접 관찰했다. '
        '진행 중이던 dapt E0/P trial은 verifier 단계에 도달했지만 API 사용량이 저장되지 않았다. '
        '완료된 행은 보존했고, 해당 trial에 입력 600k·출력 40k 한도 기준 **$0.63**을 보수적으로 예약했다. '
        '33회는 불균형·불완전하므로 확인적 재현이나 조건 간 우위의 근거로 사용하지 않는다. '
        '이는 v4 실행기의 timeout 정리 문제가 해결되었다는 뜻도 아니다.', '',
        '## 3. 보강한 통제 실험 v5', '',
        '### 공통 요구사항과 요인', '',
        '모든 조건에서 target_contract.json이 기본 요구사항이며 작업 공간의 현재 환경 근거가 입력 해석·출력 세부사항을 정하고 '
        '일반 스킬과 충돌할 때 우선한다는 지시를 동일하게 제공했다. 경로 미지시 L3와 경로 지시 L2는 구분했다. '
        '이 변경과 함께 문구·한도·입력도 달라졌으므로 v3와 v5의 차이를 권한 선언 하나의 인과 효과로 해석하지 않는다.', '',
        '| 조건 | 스킬 읽은 직후 | 첫 완료 시도 뒤 |', '|---|---|---|',
        '| B | 없음 | 완료 수용 |', '| N | 중립 진행 메시지 | 중립 완료 메시지 1회 |',
        '| C2 | 일반 전제 대조 + 파일 목록 확인 | N과 같은 중립 메시지 |',
        '| V | N과 같은 중립 메시지 | 산출물 근거 검증·수정 1회 |',
        '| P | C2와 같은 사전 확인 | V와 같은 사후 검증 |', '',
        'N/C2/V/P는 사전 확인 × 사후 검증의 2×2 비교이며 메시지 위치와 기회가 같다. '
        '실제 도구 호출 수나 문구 길이까지 같지는 않다. 중립 메시지도 행동에 영향을 줄 수 있어 N−B를 함께 본다. '
        '확인 문구는 특정 파일·파일 종류·필드·정답을 알려주지 않는다.', '',
        '### 과제·반복·모델', '',
        'graph 간선 키, csv 쉼표 해석, events 보고 시간대의 세 과제군을 사용했다. E0/E1은 입력과 계약을 공유하며 근거만 다르다. '
        'L3의 5조건 × 3과제 × 2환경 × 서로 다른 입력 5개 = 150회, L2의 B 30회를 더해 180회를 계획했다. '
        '입력 seed는 2026111001~2026111005이며 과거 실행과 겹치지 않는다. 같은 입력·과제·환경 블록 안에서 조건 순서를 섞었다. '
        '다섯 입력은 새로운 과제군 다섯 개가 아니다.', '',
        '모델은 gpt-5.4-mini-2026-03-17, reasoning low다. 요청·도구 각 20회, 300초, 누적 입력 150k·출력 20k, '
        '응답당 출력 4096 토큰 한도를 모든 조건에 적용했다. 자동 재시도는 없다. '
        'run_python은 키를 제거한 Python 하위 프로세스이며 네트워크 차단 컨테이너는 아니다. '
        '프로토콜과 실행 전 문구·코드·스킬 해시는 '+source+' 및 manifest에 있다.', '',
        '### 결과와 행동의 측정', '',
        '주 지표는 전체 정답 기준 통과, 정상 종료, 입력 파일 미변조, 기록·보관 예외 없음을 모두 만족한 비율이다. API 오류·한도 초과도 실행 성공률 분모에 남긴다. '
        '산출물 자체는 target와 반대 환경의 전체 채점기를 각각 적용해 correct, skill_consistent_mismatch, other_error, '
        'missing_output으로 분류한다. skill_consistent_mismatch는 E1에는 틀리지만 E0에 완전히 맞는 결과만 뜻한다. '
        '모델 의도나 심리적 앵커링의 직접 측정이 아니다. 혼합 오류는 전제 오적용으로 강제 분류하지 않는다.', '',
        '첫 완료 시도의 산출물을 사후 메시지 전에 복사했고, 최종 산출물도 별도로 저장했다. 채점 점수는 모델에게 보여주지 않았다. '
        '사전 확인 뒤 근거 경로의 성공한 read_file 호출은 기록하지만 Python 경유 열람을 놓칠 수 있는 하한 지표다.', '',
        '## 4. v5 결과', '',
        '**실행 완결성:** '+('계획된 모든 셀을 수행했다.' if a['complete'] else '미완료 셀이 있다. 아래 n과 계획 대비 수행 수를 함께 확인해야 한다.'), '',
        '| 과제 | 환경 | B | N | C2 | V | P |', '|---|---|---:|---:|---:|---:|---:|']
    for task in ('graph','csv','events'):
        for env in ('E0','E1'):
            vals=[frac([r for r in rows if (r['task'],r['env'],r['loc'],r['cond'])==(task,env,'L3',c)]) for c in ('B','N','C2','V','P')]
            l.append(f'| {task} | {env} | '+' | '.join(vals)+' |')
    l+=['', '### 계획한 탐색 비교', '',
        '주 관심 비교는 E1/L3의 C2−N이다. 모든 비교는 파일럿 뒤 설계한 탐색 분석이며 확증 검정으로 부르지 않는다. '
        '차이는 과제군을 동등 가중한 평균이다. 95% 구간은 과제군 재표집 10,000회(seed=20261110)다. '
        '단 세 과제군의 이산적인 기술 구간이므로 구간이 0을 넘는지만으로 일반화를 판단하지 않는다.', '',
        '| 비교 | E0 차이와 95% 구간 (%p) | E1 차이와 95% 구간 (%p) |', '|---|---|---|']
    def effect(x):
        return '미완료' if not x else f'{x["diff_pp"]:+.1f} [{x["ci95_pp"][0]:+.1f}, {x["ci95_pp"][1]:+.1f}]'
    for name in ('C2-N','C2-B','V-N','P-C2','P-V','P-N','N-B'):
        l.append(f'| {name} | {effect(a["comparisons"][name+"|E0"]["effect"])} | {effect(a["comparisons"][name+"|E1"]["effect"])} |')
    l+=['', '**E0의 [0,0] 구간에 대한 주의:** 관찰된 모든 차이가 0이어서 과제를 재표집해도 0만 나온다. '
        '이 계산은 아직 관찰하지 못한 실패나 부작용의 불확실성을 나타내지 못하며, 무해성·동등성의 근거가 아니다.', '',
        '### 사후 보충 분석: 같은 입력의 쌍과 과제 의존성', '',
        '다음 분석은 결과를 본 뒤 2026-11-10에 추가했다. 기존 비교를 대체하거나 사전 등록된 분석으로 소급하지 않는다.']
    paired=supplement['paired_c2_n']
    l+=['', f'같은 과제·입력 15쌍에서 C2만 성공 {paired["a_only"]}쌍, N만 성공 {paired["b_only"]}쌍, '
        f'둘 다 성공 {paired["both_success"]}쌍, 둘 다 실패 {paired["both_failure"]}쌍이었다. '
        f'양측 정확 McNemar p={paired["exact_two_sided_p"]:.3f}다. '
        '이는 고정된 입력 쌍들이 독립이고 영가설 아래 불일치 쌍의 부호가 교환 가능하다는 가정 아래의 민감도 검사다. '
        '15쌍을 독립 과제군 15개로 만들거나 과제군 일반화를 검증하는 분석이 아니다.', '',
        '| 제외한 과제군 | 남은 과제군의 C2−N 평균 차이 (%p) |', '|---|---:|']
    for task,diff in supplement['leave_one_family_out']['without'].items():
        l.append(f'| {task} | {diff:+.1f} |')
    l+=['', '전체 차이는 +20%p지만 graph를 제외하면 −10%p로 방향이 바뀐다. '
        '이는 집계된 긍정 방향이 graph에 의존함을 보여주는 기술적 민감도이며, 과제를 빼서 더 좋은 결과를 고르는 분석이 아니다.']
    l+=['', '### 불일치 회복과 일반 검증의 구분', '',
        '| 개입 기준 | [X−N]E1 − [X−N]E0 (%p) |', '|---|---|']
    for name,x in a['interactions'].items():l.append(f'| {name} | {effect(x)} |')
    l+=['', '### 기준선 조작 확인', '', '| 과제 | E0 B L2/L3 | E1 B L2/L3 |','|---|---|---|']
    for task in ('graph','csv','events'):
        values=[]
        for env in ('E0','E1'):
            values.append(' / '.join(frac([r for r in rows if (r['task'],r['env'],r['loc'],r['cond'])==(task,env,loc,'B')]) for loc in ('L2','L3')))
        l.append(f'| {task} | '+' | '.join(values)+' |')
    l+=['', '확인 조건의 우위가 있더라도, B의 E1 피해가 없는 과제에서는 이를 불일치로부터의 회복으로 단정하지 않는다. '
        '비유의 차이는 무효·무해성의 입증이 아니다.', '',
        '## 5. 첫 완료와 최종 산출물의 변화', '',
        '| 조건/환경 | 산출물 전이 | 횟수 |','|---|---|---:|']
    for key,transitions in a['transitions'].items():
        for transition,n in sorted(transitions.items()):l.append(f'| {key.replace(chr(124), chr(32)+chr(47)+chr(32))} | {transition} | {n} |')
    l+=['', '전이 표는 산출물 정오의 변화이며 정상 종료 여부와 별도다. 예를 들어 마지막 출력이 맞더라도 API 오류나 한도 초과면 '
        '주 성공 지표는 0이다. V와 N, P와 C2의 무작위 조건 차이가 검증 내용의 효과를 추정한다. '
        '한 실행 안에서 오답이 정답으로 바뀌었다는 사실만으로 사후 검증의 인과 효과를 확정하지 않는다.', '',
        '### 사후 단계 행동 전수 점검', '',
        '도구 호출 수와 그 행동이 나온 trial 수를 구분했다. 아래 범주는 서로 겹칠 수 있다. '
        '환경 근거는 consumer/importer.py, meta/source.json, config/report.json을 뜻하며 입력·산출물 자체와 구분한다. 근거 열람은 성공한 명시적 read_file 호출이며, Python 호출은 따로 코드를 전수 검토했다.', '',
        '| 조건/환경 | n | 도구 없음 | 산출물 read_file | Python 실행 | write_file | 실제 산출물 변화 | 새 근거 read_file |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key,d in supplement['post_groups'].items():
        l.append(f'| {key} | {d["n"]} | {d["no_tool_trials"]} | {d["output_read_trials"]} | '
                 f'{d["python_trials"]} | {d["write_file_trials"]} | {d["artifact_changed_trials"]} | {d["evidence_read_trials"]} |')
    l+=['', 'V/P의 60 trial에서 사후 단계의 새 근거 read_file은 0회였다. '
        'Python 15개도 전부 읽어 확인했으며 입력·산출물 비교만 하고 환경 근거를 새로 읽지는 않았다. '
        '사전에 읽은 근거를 내부적으로 활용할 가능성은 남는다. 따라서 이번 검증 지침의 행동 유도 실패를 '
        '실제로 근거를 대조한 검증 방법 자체의 무효로 해석하지 않는다. '
        '[코드 전수 검토](../experiments/E02-skill-precheck/analysis/V5_POST_PYTHON_REVIEW.md)와 '
        '[보충 원자료](../experiments/E02-skill-precheck/analysis/v5_sensitivity.json)를 함께 제공한다.', '',
        '## 6. 비용·오류·실행 검증', '', '| 조건(L3) | 시행 | 성공 | 회당 비용($) | 평균 도구 호출 |','|---|---:|---:|---:|---:|']
    for c,d in a['by_condition_hidden'].items():
        l.append(f'| {c} | {d["n"]} | {d["success"]}/{d["n"]} | {d["mean_cost_usd"] or 0:.6f} | {d["mean_tool_calls"] or 0:.1f} |')
    l+=['', '### 조건별 자원과 중단 사유(L3)', '', '| 조건 | 입력 토큰 | 출력 토큰 | 요청 수 | 도구 수 | 중단 사유 |', '|---|---:|---:|---:|---:|---|']
    for cond,d in a['resources_hidden'].items():
        l.append(f'| {cond} | {d["input_tokens"]} | {d["output_tokens"]} | {d["requests"]} | {d["tools"]} | {d["stops"]} |')
    l+=['', '### 셀별 수행/계획', '', '| 과제/환경/위치/조건 | 수행/계획 | 성공 | 오류 |', '|---|---:|---:|---:|']
    for key,d in a['cells'].items():
        l.append(f'| {key} | {d["n"]}/{d["expected"]} | {d["success"]}/{d["n"]} | {d["errors"]} |')
    total_prior=sum(x['known_usd']+x['unknown_billing_upper_usd'] for x in manifest['prior_budget_ledger'])
    l+=['', f'이번 작업 전체의 보수적 예산 합계는 **${total_prior+manifest["conservative_spent_usd"]:.6f}** '
        '(기존 미기록 trial 최대 $0.63 포함)다. 사용자 허용 $10 안에서 수행했다. '
        '비용은 [공식 단가](https://developers.openai.com/api/docs/models/gpt-5.4-mini)의 입력 $0.75/M·출력 $4.50/M을 '
        '사용한 캐시 할인 전 추정이며 청구서 금액이 아니다.', '',
        f'상태 집계: `{dict(Counter(r["status"] for r in rows))}`. '
        f'입력 변조 {sum(r["input_modified"] for r in rows)}회, 누출 경고 {sum(bool(r["leak_flags"]) for r in rows)}회, '
        f'기록/진단 예외 {sum(bool(r.get("archive_errors")) for r in rows)}회.', '',
        '오프라인 검증은 기존 채점·조작 점검 216개, 새 입력의 정답/반대 환경 분류 120개, '
        '예산 경합·혼합 오류·사후 snapshot·중립 메시지·기한 초과·출력 폴더 삭제 회귀 테스트를 포함한다. '
        '모의 180회는 배관 점검이고 성능 결과에서 제외했다.', '',
        '## 7. 해석의 범위와 다음 단계', '',
        '이 장의 기여는 새로운 범용 검증 알고리즘의 입증보다, 스킬 적용 실패를 탐색·산출물 전제·일반 구현 오류로 '
        '구분하고, 중립 기회와 사전/사후 개입을 분리해 측정할 수 있는 재현 가능한 실험으로 정리한 데 있다.', '',
        '- C2는 전제 대조와 작업 공간 목록 탐색을 함께 제공한다. 목록 탐색만 하는 조건이 없어 두 요소를 분리하지 못한다.',
        '- 스킬 없음 A가 없다. B의 E0/E1 차이는 고정 스킬 아래 환경 불일치 민감도를 보이며, 스킬 제공 자체가 해를 끼쳤다는 인과 효과는 식별하지 않는다.',
        '- 범위는 합성 통제 과제 세 군, 모델 하나, reasoning 설정 하나다. graph는 토폴로지가 고정되고 간선 순서·일부 화자 속성만 달라진다. 새 입력 5개를 폭넓은 새 문제 5개로 보지 않는다. 자연 발생 스킬 오류와 다른 모델로 일반화하지 않는다.',
        '- 기존 결과를 보고 설정을 바꿨다. 새 입력은 과거 입력 재사용을 피하지만 설계 선택 편향을 없애지 않는다.',
        '- 중립·검증 메시지의 길이와 실제 도구 사용량은 다르다. 이 비교는 각 정책 전체의 효과다.',
        '- 반대 환경과 일치하는 오답은 스킬과 호환되는 결과라는 뜻이며, 모델이 스킬 때문에 그 답을 골랐다는 증명은 아니다.',
        '- v3/v5의 요구사항·문구·한도·입력이 함께 달라졌다. 두 버전 차이를 권한 선언의 단독 효과로 해석하지 않는다.',
        '- 공개 과제 Hidden 변형과 timeout 프로세스 정리, 네트워크 격리, 다른 러너의 교차 재현은 후속 과제다.', '',
        '## 8. 재현과 원자료', '',
        '- [v5 프로토콜](../experiments/E02-skill-precheck/analysis/V5_PROTOCOL.md)',
        '- [실행 manifest](../experiments/E02-skill-precheck/results/v5/report-v5-001/manifest.json)',
        '- [전체 trial](../experiments/E02-skill-precheck/results/v5/report-v5-001/trials.jsonl)',
        '- [분석 JSON](../experiments/E02-skill-precheck/results/v5/report-v5-001/analysis.json)',
        '- [기존 결과의 비판적 검토](../experiments/E02-skill-precheck/presentation/w6/RESEARCH_MEMO.md)',
        '- [독립 설계 검토](../experiments/E02-skill-precheck/analysis/DESIGN_REVIEW.md)', '',
        'API 없는 집계 재현:', '', '```sh', 'cd experiments/E02-skill-precheck',
        'python3 src/analyze_v5.py results/v5/report-v5-001', 'python3 src/sensitivity_v5.py', 'python3 src/build_chapter.py', '```', '',
        '유료 재실행은 명시적인 예산 승인 후 새 run-id로만 수행한다. run_v5.py는 이전 실제 v5 실행까지 합산해 '
        '세션 승인 금액을 계산하고 동시 요청마다 비용을 예약한다. 기존 실행과 새 실행의 비용을 별도 한도로 중복 승인하지 않는다.']
    l+=['', '## 부록 A. 과제별 산출물 전이', '',
        '| 과제/조건/환경 | 첫 완료 → 최종 | 횟수 |', '|---|---|---:|']
    for key,transitions in a['transitions_by_task'].items():
        for transition,n in sorted(transitions.items()):
            l.append(f'| {key.replace(chr(124), " / ")} | {transition} | {n} |')
    interpretation=EXP/'analysis/V5_INTERPRETATION.md'
    if interpretation.exists():
        at=l.index('## 7. 해석의 범위와 다음 단계')+2
        l.insert(at,interpretation.read_text().strip())
    summary_counts={c:frac([r for r in rows if r['env']=='E1' and r['loc']=='L3' and r['cond']==c]) for c in ('B','N','C2','V','P')}
    summary='E1/L3 성공 수는 '+', '.join(f'{c} {n}' for c,n in summary_counts.items())+'였다. 과제별 차이와 사후 수정 여부를 함께 해석한다.'
    l.insert(l.index('## 1. 문제와 선행연구'),summary+'\n')
    (ROOT/'report/e02-skill-precheck.md').write_text('\n'.join(l)+'\n')
    print(ROOT/'report/e02-skill-precheck.md')

if __name__=='__main__':main()
