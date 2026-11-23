# E03 — 공통 벤치마크 테스트 환경 구성

> 이 PR 은 **설계·뼈대 단계**다. 실제 모델·API 를 호출한 파일럿은 아직 없다. 아래 "파일럿 관찰"은 미실시로 표시했다.

## 신원과 상태
- 실험 ID: E03
- 담당자 / 공동 작성자: DonghoonPark12
- 단계: 설계 (파일럿 전)
- 실행 모드: 실행 전 — 모델·API 호출 없음. 오프라인 테스트와 `--dry-run` 만 실행
- 작성일 / 실행 commit: 2026-10-27 / 실행 없음 (코드는 제출자 로컬 개발 저장소 `56aba30` 에서 복사, dirty 아님)

## 연구 질문과 가설
- 질문: LoCoMo·LongMemEval 에서 메모리 저장 알고리즘만 바꾸고 답변기·judge·top-k·지표·정답 정보 접근을 고정하면,
  알고리즘 간 점수 차이를 메모리 알고리즘의 차이로 해석할 수 있는 평가 환경을 만들 수 있는가?
- 가설과 근거: 공개된 메모리 시스템 평가는 시스템마다 평가 코드가 달라 점수 차이에 평가 조건 차이가 섞인다.
  - Mem0 논문 계열 평가([memodb-io/memobase `docs/experiments/locomo-benchmark`](https://github.com/memodb-io/memobase/tree/358c16b/docs/experiments/locomo-benchmark))와
    mem0 공식 러너([mem0ai/memory-benchmarks](https://github.com/mem0ai/memory-benchmarks/tree/4b61c5d))는 같은 LoCoMo 에서도
    적재 단위(2턴/1턴)·화자 처리·검색 개수(화자당 10/최대 200)·답변 프롬프트·judge 모델(gpt-4o-mini/gpt-5)이 다르다.
  - Jev-Mem([arXiv:2609.23986](https://arxiv.org/abs/2609.23986), 코드 [libingzheren/Jev-Mem@7ab0c73](https://github.com/libingzheren/Jev-Mem/tree/7ab0c73))
    평가 코드는 데이터셋의 정답 카테고리로 답변 프롬프트·top-k 를 고르고, 답변자에게 메모리를 40~50개 넘긴다.
  - 그래서 (1) 알고리즘은 적재·검색만 하고 (2) 답변·채점·집계는 모든 알고리즘에 같은 조건으로 하며
    (3) 정답·카테고리·근거 표시를 알고리즘 프로세스에 넘기지 않으면 비교가 가능해진다고 본다. 설계는 [DESIGN.md](DESIGN.md).

## 비교 설계
- 태스크 / 데이터 버전·출처·분할: LoCoMo-10 (대화 10, cat1–4 1,540문항), LongMemEval-S cleaned (질문 500).
  출처·버전·체크섬·사용 조건은 [data/README.md](data/README.md). 둘 다 공개 테스트 세트 하나뿐이라 파일럿용·최종 평가용 분할은 미정.
- Baseline: [configs/baseline.json](configs/baseline.json) — 기준 메모리 알고리즘 **미정** (후보: Mem0 논문 방식 재구성)
- Intervention: [configs/intervention.json](configs/intervention.json) — 새 메모리 저장 알고리즘 `idea1` (**미구현**)
- 고정 조건: 답변 모델 gpt-4o-mini, judge (LoCoMo gpt-4o-mini · LongMemEval gpt-4o-2024-08-06), top_k 10,
  지표 LLM-as-a-judge·F1·BLEU-1, 공통 답변 프롬프트(`--answer-mode harness`). 버전 고정 snapshot 은 실행 시 manifest 에 기록 예정
- 개입 적용 확인: 어댑터 `setup()` 반환값(알고리즘 버전·하이퍼파라미터)과 문항별 검색 결과를 `records.jsonl` 에 기록 예정
- 채점: LoCoMo 는 mem0-evaluation `ACCURACY_PROMPT`, LongMemEval 은 공식 질문 유형별 judge 5종 + abstention.
  F1·BLEU-1 은 mem0-evaluation `metrics/utils.py` 정의. 구현·수동 확인 사례는 아직 없음
- 반복·실행 순서·seed: 미정 (기본 1회, 논문 비교 시 10회 평균 ± 표본 SD). 에피소드 단위 병렬, seed 42 (모델 sampling seed 지원 여부는 미확인)
- 예산과 중단 조건: 미정. 실행기에 LLM 호출 수 상한과 체크포인트 재개를 넣을 계획

## 파일럿 관찰

| 항목 | Baseline | Intervention |
| --- | --- | --- |
| 성공 수 / 모든 시도 수 | 미실시 | 미실시 |
| 모든 반복 성공 태스크 수 / 전체 태스크 수 | 미실시 | 미실시 |
| 시간·토큰·비용 | null — 실행 전 | null — 실행 전 |

- 실행 기록: 없음 (`results/pilot/` 비어 있음)
- 이번에 확인한 것 (API 없음):
  - `src/tests/test_adapter_ipc.py` 2건 통과 — 예시 어댑터를 작업 프로세스로 띄워 setup·reset·ingest·retrieve 왕복,
    어댑터 예외가 `AdapterError` 로 전달되고 프로세스가 계속 응답함
  - `run.py --list`, `run.py --algorithm example --benchmark locomo --eval-metric F1 LLM-as-a-judge --dry-run` 정상 출력
  - 데이터 다운로드 URL 2개(LoCoMo, LongMemEval oracle)로 받은 파일의 체크섬이 data/README.md 와 일치
- 난이도와 비용에 대한 관찰: 미측정. 참고로 제출자가 별도 코드로 Mem0 논문 방식(턴마다 LLM 2회)을 LoCoMo 전체 1회 돌릴 때
  LLM 호출 상한 약 13,700회·약 7달러(gpt-4o-mini)로 추정했다. 이 PR 의 코드로 잰 값이 아니다

## 설계 변경과 최종 태스크

| 파일럿 관찰 | 변경 내용과 이유 | 최종 설정 |
| --- | --- | --- |
| 파일럿 미실시 | 변경 없음 | 미정 |

- 본 실험 계획: 데이터 로더 → 지표·judge → 공통 답변기 → 실행기(체크포인트·재개) → 결과 집계 순으로 구현한 뒤,
  LongMemEval oracle·LoCoMo 일부 대화로 소규모 파일럿을 먼저 돌린다. 구현 순서와 미결정 사항은 [DESIGN.md](DESIGN.md)
- 파일럿에서 튜닝에 사용한 태스크와 최종 평가 표본의 관계: 미정

## 해석과 한계
- 현재 근거로 말할 수 있는 것: 알고리즘별 가상환경 분리와 공통 평가 환경 ↔ 알고리즘 통신 경로가 오프라인에서 동작한다.
- 실패·부정적 결과 / 한계: 평가 결과가 없다. 공통 답변 프롬프트를 고정하면 알고리즘 고유 답변 방식을 쓰는 원 논문 수치와는
  달라진다(원 논문 재현은 `--answer-mode native` 로 따로 표시할 계획).
- 아직 확인하지 못한 것: 실제 모델 호출, 채점기 정확성, 시간·비용, 기준 알고리즘 선정.

## 교차 재현
- 재현자 / 원본 commit / 결과 경로: 미실시
- 동일 조건 결과와 차이·해석: 미실시
