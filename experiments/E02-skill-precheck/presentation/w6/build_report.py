"""Format the offline evidence export as a presentation and review companion."""
import json
from pathlib import Path

P=Path(__file__).resolve().parent
E=json.loads((P/'evidence.json').read_text())
R=E['runs']
lines=['# W6 추가 실험 결과 · 2026-11-09', '',
       '기존 파일럿을 재현하는 추가 실행이다. 최종 설계의 700회 본실험은 수행하지 않았다. '
       '기존 실행과 새 실행은 합치지 않는다. 모든 실행 trial을 분모에 넣고 API·인프라 오류도 비성공으로 센다. '
       '과거 CARD.md의 SkillsBench 수치는 API 오류를 제외하므로 아래 표와 분모가 다를 수 있다.', '',
       f'새 실행 비용 합계 **${E["new_cost_usd"]:.6f}**. 사용자 허용 $10, 계획 합계 상한 $9. '
       'Responses usage에 입력 $0.75/M·출력 $4.50/M을 곱한 캐시 할인 전 리스트 가격 추정치다. 청구서 금액이 아니다.', '',
       '## 실행 완결성', '', '| 실행 | 수행/계획 | 성공 | 오류 | 비용($) |', '|---|---:|---:|---:|---:|']
for name,run in R.items():
    s=run['total']
    lines.append(f'| {name} | {run["completed"]}/{run["planned"]} | {s["success"]}/{s["n"]} | {s["errors"]} | {s["cost_usd"]:.6f} |')
lines+=['', '## 통제 과제 · E1/L3', '',
        '스킬이 맞지 않고 근거 파일을 지시하지 않은 칸. 새 입력 seed=20261109, 순서 seed=1109, '
        '같은 모델·문구·도구·채점기·한도. 조건별 칸당 5회. v3의 C2는 소비자 코드·설정·출처 메타데이터라는 '
        '위치 유형을 알려주는 문구이며 최종 설계 문구와 다르다.', '',
        '| 실행 | 과제 | B | C | C2 |', '|---|---|---:|---:|---:|']
for name in ('v3_original','v3_replication'):
    for task in ('graph','csv','events'):
        ss=[R[name]['cells'][f'{task}/E1/L3/{c}'] for c in ('B','C','C2')]
        lines.append(f'| {name} | {task} | '+' | '.join(f'{s["success"]}/{s["n"]}' for s in ss)+' |')
    c=R[name]['comparisons']['C2-B']
    lines += ['', f'**{name} C2−B**: 과제 평균 {c["diff_pp"]:+.2f}%p, 과제 재표집 95% 구간 {c["ci95_pp"]}.', '']
lines+=['과제 단위 구간은 10,000회 부트스트랩(seed=20261109)이다. 과제가 3개뿐이므로 모집단 일반화나 '
        '최종 H1의 확증으로 해석하지 않는다. 기존 카드의 trial 독립 Newcombe 구간과 계산 단위가 다르다.', '',
        '## SkillsBench · E1', '',
        '기존 여섯 과제를 모두 유지했다. 과제 입력은 기존 실행과 같고, 새 모델 요청으로 재실행했다. '
        '새 실행은 칸당 2회다. P는 C2에 완료 전 검증을 추가한다. N·V·Hidden 가시성 조작은 아직 적용하지 않았다.', '',
        '| 실행 | 과제 | B | C2 | P |', '|---|---|---:|---:|---:|']
for name in ('v4_original','v4_replication'):
    for task in R[name]['plan']['tasks']:
        ss=[R[name]['cells'][f'{task}/E1/native/{c}'] for c in ('B','C2','P')]
        lines.append(f'| {name} | {task} | '+' | '.join(f'{s["success"]}/{s["n"]}' for s in ss)+' |')
    for comparison in ('C2-B','P-C2'):
        c=R[name]['comparisons'][comparison]
        lines+=['',f'**{name} {comparison}**: 과제 평균 {c["diff_pp"]:+.2f}%p, 과제 재표집 95% 구간 {c["ci95_pp"]}.']
lines+=['', '이 비교는 탐색적이다. 과거 P 신호를 본 뒤 골랐고, 단독 검증 V와 위약 N이 없다. '
        '특히 이 원본 과제군에서는 E1이 B 성능을 낮추는지(M1)부터 확인해야 한다. '
        '정답 값이 지시문에 있는 과제 4개와 원래 근거가 다른 파일에 있는 과제 2개는 구분해야 한다.', '',
        '## 정상 환경과 비용', '', '| 실행 | 조건 | E0 성공 | 전체 회당 비용($) |', '|---|---|---:|---:|']
for name,run in R.items():
    for cond,s in run['by_condition'].items():
        vals=[v for k,v in run['cells'].items() if k.split('/')[1]=='E0' and k.split('/')[3]==cond]
        lines.append(f'| {name} | {cond} | {sum(v["success"] for v in vals)}/{sum(v["n"] for v in vals)} | {s["cost_usd"]/s["n"]:.6f} |')
lines+=['', '## 근거 열람 대리 지표', '',
        'evidence_opened는 도구 인자에 경로나 파일명이 등장했는지로 계산한 기존 지표다. '
        '실제 열람 성공·이해·적용의 증거로 간주하지 않는다. 실패 사례는 반환 내용과 작성 코드를 직접 확인했다.', '',
        '| 실행 | 조건 | 근거 경로 등장 | 그중 성공 |', '|---|---|---:|---:|']
for name,run in R.items():
    for cond,m in run['mechanism'].items():
        lines.append(f'| {name} | {cond} | {m["opened"]}/{m["n"]} | {m["success_opened"]}/{m["opened"]} |')
lines+=['', '## 실패 궤적', '',
        '기존 main-002의 events-E1-L3-C2-r1. trace items[10–11]의 read_file 반환에 '
        '`report_timezone: Asia/Seoul`이 있다. 이후 items[19]의 Python 코드가 '
        '`day=row[\'ts_utc\'][:10]`으로 UTC 날짜를 잘라 쓰고, items[25]에서 그 결과를 저장했다. '
        '채점 이유는 `premise_from_other_env`. 한 사례의 메커니즘 예시이며, 빈도·인과 효과의 추정이 아니다.', '',
        '## 남은 구현과 다음 실험', '',
        'CARD.md 최종 설계의 N·V 조건, 일반화한 C2 문구, SkillsBench Hidden 변형, 통제 과제 Docker 포팅, '
        'verifier 사전 의존성 설치·오프라인 실행, 재개 기능, 전체 스킬 폴더 해시, 실패 테스트 이름 기록 등이 남아 있다. '
        '이번 작업은 기존 실행기를 사용한 독립 재현이며 이 구현을 완료했다고 주장하지 않는다. '
        '최종 본실험 700회의 예상 비용은 약 $26으로 이번 $10 승인 범위에 들어가지 않는다.', '',
        '## 출처와 재현', '',
        '- [W6·W7 발표 안내](https://app.notion.com/p/40f780c0050b81fea0a6d137a7a9d799): 11/10 21:00, 장현서 4번째, 장표 마감 20:00.',
        '- [개인 설계 노션](https://app.notion.com/p/3f7780c0050b816b937bed1bc6bdc27d): 이전 파일럿과 최종 설계.',
        '- [SkillsBench](https://arxiv.org/abs/2602.12670), [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401), [Demystifying Agent Skills](https://arxiv.org/abs/2608.14036). '
        'SWE-Skills-Bench는 2026-10-27 v2로 개정되어, 노션의 이전 49개 스킬 수치를 현재 논문 수치로 재사용하지 않았다.',
        '- [모델 단가](https://developers.openai.com/api/docs/models/gpt-5.4-mini): 2026-11-09 확인.',
        '- 로컬 기준 Agentproof@1095fba26ba6a66056eee4cc2c3b1e8f27f94adf. 실행 manifest의 코드·문구·스킬 해시 참조.',
        '', '집계와 장표 재생성(API 호출 없음):', '', '```sh',
        'cd experiments/E02-skill-precheck', 'python3 src/w6_report.py',
        'python3 presentation/w6/build_report.py', 'python3 presentation/w6/build_deck.py', '```', '',
        'API 재실행은 별도 명시적 승인 뒤 새 run-id로만 수행한다. 실행 계획은 '
        '`configs/plan_w6_replication.json`, `sb/plan_w6_replication.json`에 있다.', '',
        '## 전체 셀', '', '| 실행 | 과제/환경/위치/조건 | 성공 | 오류 | 비용($) |', '|---|---|---:|---:|---:|']
for name,run in R.items():
    for k,s in sorted(run['cells'].items()):
        lines.append(f'| {name} | {k} | {s["success"]}/{s["n"]} | {s["errors"]} | {s["cost_usd"]:.6f} |')
(P/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(P/'REPORT.md')
