# E05 — Memory Applicability Judgment (과거 실패 경험 적용 가능성 판단과 상충 관계 분석)

LLM 에이전트가 과거 실패 경험(Memory)을 참고하여 현재 실행 궤적(Trajectory)의 실패 원인을 진단할 때, 검색된 Memory가 현재 상황에 적절한지 스스로 구별하고 이를 최종 진단에 일관되게 반영할 수 있는지 검증합니다. 연구 배경, 4단계 파일럿 실험 진행 과정, 관찰된 수용-거부 상충 관계(Acceptance–Rejection Trade-off) 및 후속 본실험 설계는 [`CARD.md`](CARD.md)에 정리되어 있습니다.

## 요구 사항

- Python 3.10+ (표준 라이브러리만으로 공식 `harness/summarize.py` 검증 및 [`src/analyze.py`](src/analyze.py) 실행 가능)
- 실제 LLM API 재실행 시: OpenRouter API 키 (`.env`에 `OPENROUTER_API_KEY` 설정, 커밋 금지)

## 실행 및 검증 방법 (레포 루트에서 실행)

API 키나 외부 패키지 없이 저장된 파일럿 실행 로그 4종을 검증하고 [`CARD.md`](CARD.md)의 모든 수치를 즉시 재현할 수 있습니다.

```sh
# 1) AgentProof 공식 집계기(harness/summarize.py)로 4단계 파일럿 로그 검증
python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/pilot-initial-n100
python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/pilot-factorial-n100
python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/pilot-comparative-n159
python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/pilot-span-tradeoff-n159

# 2) CARD.md 3.1~3.4절의 전체 정확도 및 유익한/해로운 교정(Beneficial/Harmful Override) 표 재현
python3 experiments/E05-memory-applicability/src/analyze.py

# 3) 원자료로부터 새로운 run-id 폴더 재생성 점검 (기존 run-id는 덮어쓰지 않음)
python3 experiments/E05-memory-applicability/src/run.py --run-id verify-001 --stage span-tradeoff
python3 harness/summarize.py experiments/E05-memory-applicability/results/pilot/verify-001
```

## 폴더 구성

| 경로 | 설명 |
| --- | --- |
| [`CARD.md`](CARD.md) | 연구 질문(RQ1·RQ2), 실험 진행 과정(3.1~3.5절), 실제 로그 사례, 한계 및 후속 통제 실험 설계 |
| [`configs/baseline.json`](configs/baseline.json) | 기준선 설정 (보수적인 비교 적용성 검토 `D5`, `google/gemma-4-31b-it`, `temperature=0.0`, `seed=42`) |
| [`configs/intervention.json`](configs/intervention.json) | 개입 설정 (구간 구조를 강화한 비교 판단 `D6-G`, 동일한 모델·검색·디코딩 조건) |
| [`data/tasks.json`](data/tasks.json) | 평가 대상 태스크 289개(`pilot_n30`, `test_n100`, `eval_n159`)의 목표 구간, 정답 실패 라벨, 검색된 Memory 메타데이터 |
| [`data/split.json`](data/split.json) | Goal 단위 무누수 데이터 분할(`seed=42`, Memory Bank / Pilot / Test) 기록 |
| [`src/prompts.py`](src/prompts.py) | 7개 실패 분류 체계(Taxonomy) 및 비교 적용성 프롬프트 템플릿 |
| [`src/run.py`](src/run.py) | AgentProof 표준 포맷(`manifest.json`, `trials.jsonl`, `summary.json`) 생성 및 검증 실행기 |
| [`src/analyze.py`](src/analyze.py) | [`CARD.md`](CARD.md)에 보고된 단계별 정확도, 유익한 교정(`W→C`), 해로운 교정(`C→W`) 집계 스크립트 |
| [`results/pilot/`](results/pilot/) | AgentProof 표준 규격을 통과하는 4개 파일럿 단계별 실행 로그 (`manifest.json`, `trials.jsonl`, `summary.json`) |
| [`results/raw/`](results/raw/) | 각 조건의 세부 출력(`t_init`, `t_mem`, `supp_steps`, `cont_steps`, `decision`)이 보존된 전체 원자료 JSON/CSV |

## 알려진 차이·한계

- 본 실험의 평가 모델 호출은 OpenRouter(`google/gemma-4-31b-it`, `temperature=0.0`)를 통해 수행되었으며, 로컬 응답 캐시 구조상 개별 trial 단위의 응답 시간(`latency_ms`)과 토큰 사용량(`input_tokens`, `output_tokens`, `cost_usd`)은 `null` 및 `missing_reasons`로 명시하였습니다(전체 파일럿 누적 API 사용액 약 `$5.03`).
- [`CARD.md`](CARD.md) 5절에 기술된 Paired Memory Swap(`M+`/`M−` 쌍대 교체) 및 대칭적 근거 비교 실험은 API 한도 도달로 인해 본실험 계획으로만 사전 등록되어 있으며 아직 실행하지 않았습니다.
