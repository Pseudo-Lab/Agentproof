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
