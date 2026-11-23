# E04 Plan 품질·비용 파일럿

이 디렉터리는 2026-10-25 실행된 Plan Benchmark 파일럿의 결과를 AgentProof 형식으로 정리합니다. 기존 모델 호출은 다시 실행하지 않았습니다. `src/build_submission.py`는 원본 run 디렉터리를 지정해 결과 보관본과 baseline/intervention 쌍별 로그를 오프라인으로 재구성합니다.

## 파일럿 결과

`results/pilot/overall_summary.md`에서 A/B/C 점수와 비용, pairwise bootstrap 비교, 재시도 기록의 비용 하한을 확인하세요. 원본 상세 Plan·judge 근거와 축약 call ledger는 `results/pilot/source/`에 있습니다. AgentProof 표준 로그와 공식 요약은 `pairwise-ab-001/`, `pairwise-ac-001/`에 저장됩니다.

실행 전 원본 기록을 재구성하려면 저장소 루트에서 Python 3.10+로 실행하세요:

```powershell
python experiments/E04-plan-quality-cost/src/build_submission.py --source-run "<원본 run 폴더>"
```

원본 자료가 `results/pilot/source/`와 `data/tasks.json`에 이미 있으면:

```powershell
$env:PYTHONUTF8 = "1"
python experiments/E04-plan-quality-cost/src/build_submission.py
```

공식 로그 검증 및 요약:

```powershell
python harness/summarize.py experiments/E04-plan-quality-cost/results/pilot/pairwise-ab-001
python harness/summarize.py experiments/E04-plan-quality-cost/results/pilot/pairwise-ac-001
```

`PYTHONUTF8=1`은 Windows 기본 코드페이지가 UTF-8 JSONL 파일을 읽지 못하는 환경에서 필요합니다. 빌더는 모델/API를 호출하지 않습니다. 실행 당시 Promptfoo/Python 버전, 조건 설명, 원본 source hash 및 invocation은 `results/pilot/source/`에 기록되어 있습니다.

## 해석 주의

이 실행은 초기 계획의 Claude planner 비교 및 코드 이슈 실행 평가와 다릅니다. 실제로는 GPT 계열 모델이 12개 계획 태스크를 작성했고 계획 품질만 채점했습니다. 최신 셀 기준 평균 A=96.11, B=89.70, C=90.75이며 B/C는 A 대비 사전 설정한 5점 비열등성 기준을 입증하지 못했습니다. B는 더 저렴했고 C는 B보다 소폭 높은 점수와 더 높은 비용을 보였습니다. 생성 오류 9건과 누락된 API 비용을 반드시 함께 고려하세요. 자세한 변경 내역과 재현성 한계는 [CARD.md](CARD.md)에 적었습니다.

## 2026-11-02 후속 파일럿

Plan 품질만 측정하는 범위는 유지하고 모델별 completion-token 상한을 6,000에서 12,000으로 올렸습니다. 고정된 도전 태스크 4개, 별도 judge 모델, judge 사전 점검 4회, 생성·종합·채점 호출별 사용량 기반 비용 기록을 추가했습니다. 2026-10-25 파일럿은 이전 실행 자료로 보존하며, 아래는 별도 후속 실행입니다.

16개 태스크 × 5조건 × 3회 반복으로 총 240개 셀을 비교했습니다. A는 `gpt-6.1-sol` 단일 실행, B는 `gpt-6-luna` 단일 실행, C는 같은 역할의 경량 후보 3개와 종합기, D는 같은 역할의 후보 5개와 종합기, E는 역할을 나눈 경량 후보 3개와 종합기입니다. Plan은 생성 후 별도 모델 `gpt-6.1-terra`가 채점했습니다. 75/100점 이상이며 중대 오류가 없어야 통과합니다. 사람 평가는 포함하지 않았고, 실제 태스크 실행도 측정하지 않았습니다.

| 조건 | Plan 점수 /100 | 통과율 | 추정 총비용 |
|---|---:|---:|---:|
| A | 94.09 | 94% | $2.071655 |
| B | 77.66 | 67% | $0.438010 |
| C | 84.30 | 90% | $0.810089 |
| D | 83.83 | 75% | $1.064201 |
| E | 84.30 | 81% | $0.866505 |

최고 점수의 다중 에이전트 조건(C/E)도 A보다 9.79점 낮았습니다. C-A의 태스크 군집 bootstrap 95% 구간은 [-12.84, -6.77]입니다. 동질 역할 에이전트를 3개에서 5개로 늘린 D는 평균 점수를 높이지 못했고 비용은 더 들었습니다. 240개 결과 모두 사용량 비용을 계산할 수 있었고 API 오류는 없었습니다. B에서 Plan JSON 계약 위반 1건은 0점 처리했습니다. 본 실험 추정 지출은 $5.250461이며, 별도 judge 점검 비용 $0.011775는 이에 포함되지 않습니다. 층별 결과와 paired 비교, 한계는 `results/followup-20261102/summary.md`와 `summary.json`을 보세요.

상세 자료는 `results/followup-20261102/`에 있습니다. 태스크와 judge 전용 기준, 반복별 CSV, Plan 및 후보 출력, 채점 근거, 호출 비용·토큰, judge calibration, 실행 설정과 소스 코드를 보관했습니다. 실행 당시 checkout은 dirty였고, 실행 manifest의 소스 해시와 보관한 현재 코드 스냅샷은 `run.py`, `resume_run.py`에서 일치하지 않습니다. 이 차이를 포함한 재현성 한계는 manifest에 기록했습니다.