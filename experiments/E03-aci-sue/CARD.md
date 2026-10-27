# E03 — S/U/E 도구 인터페이스와 코딩 에이전트의 효율

- 담당자: [muuty](https://github.com/muuty)
- 단계: 실제 모델 파일럿. 실행 2026-10-26 UTC, 제출 정리 2026-10-27.
- 질문: 기존 Search / Understanding / Editing 도구를 제공하고 사용 경로를 제한하면 해결률과 시간·토큰 사용이 어떻게 달라지는가?
- 가설: 구조화된 검색·읽기·편집은 탐색 낭비를 줄일 수 있다. 이번에는 도구 사용과 에이전트 연동부터 점검했다.

## 비교

| 항목 | Baseline | Intervention |
| --- | --- | --- |
| 설정 | [baseline.json](configs/baseline.json) | [intervention.json](configs/intervention.json) |
| 실행 | mini-swe-agent 기반 bash | mini 기반 단계별 named tool |
| S | 셸 검색 | AutoCodeRover 검색 API 8개 |
| U | 셸 읽기 | CodeStruct readCode |
| E | 셸 편집 | CodeStruct editCode / str_replace / create_file |
| 전환 | 자유 선택 | 초기 S→U→E, 이후 복귀 가능 |
| 검증·제출 | 셸 테스트·patch.txt | run_tests(pytest/Django)·view_diff·submit |
| 호출 | 응답당 복수 허용 | 응답당 하나 |
| 프롬프트 | bash 지침 | 단계·도구·검증·제출 지침 |
| 오류 처리 | format error 상한 3, API retry 억제 | 상한 0, deadline 내 원본 retry |

mini 2.4.6, 공식 SWE-bench 4.1.0과 기존 도구를 사용했다. [원본 commit](configs/upstreams.lock.json),
[실행 코드·해시](src/snapshots/provenance.json), [도구 schema](configs/intervention-tools.json)를 포함한다.
CodeStruct의 UTF-8 위치 수정은 snapshot의 tools/*/patches에 기록했다. U는 CodeStruct를 사용했다.

- 데이터: SWE-bench Lite test revision `6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`의 [기존 점검용 5문제](data/tasks.json).
- 표본: 모델별 5문제 × 2조건 × 1회 = 총 20건. 앞선 실험에서 사용한 문제다.
- 예산: 문제당 600초, 요청·step 상한 없음. 준비·인덱싱·공식 채점은 별도. 종료 후 패치 회수 최대 30초.
- 모델: Gemma-4-31B-it / Qwen3.5-27B, seed 42, thinking 활성화, 모델별 1 worker. revision과 sampling은 manifest에 저장했다.
- 순서: 기존 bash baseline 배치와 이후 audited staged 배치를 비교했다. staged는 Gemma→Qwen 순서다.
- 채점: 제출을 마친 뒤 공식 SWE-bench evaluator 사용. 빈 패치도 분모에 포함한다.

## 결과

| 모델·조건 | 해결 | 평균 시간 | 입력 토큰 합 | 출력 토큰 합 | 요청 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma baseline | 3/5 | 425.8초 | 1,992,385 | 43,794 | 147 |
| Gemma staged | 3/5 | 400.8초 | 2,038,583 | 40,239 | 147 |
| Qwen baseline | 4/5 | 337.0초 | 3,293,704 | 39,565 | 206 |
| Qwen staged | 1/5 | 229.2초 | 4,672,640 | 23,740 | 139 |

- Gemma는 같은 3문제를 해결했다. Qwen은 빈 패치 1건과 재현 파일만 제출한 2건에서 일찍 종료했다.
- Staged 10건 모두 S/U를 사용했고, 제품 코드 수정은 7건이었다. [실패 9건 분석](FAILURES.md)
- Agent timeout·공식 채점 실행 오류는 0건. 도구 오류는 trajectory에 보존했다.
- 시간은 native 정수 초, 토큰은 저장된 API usage 합이다. GPU 비용은 미측정으로 `null` 처리했다.
- [Gemma 기록](results/pilot/E03-gemma31b-historical-pilot5/manifest.json), [Qwen 기록](results/pilot/E03-qwen27b-historical-pilot5/manifest.json): 각각 manifest/trials/summary와 원본 형식 evidence를 포함한다.
- 채점 확인: 성공한 Xarray, 실패한 Astropy, 빈 패치 Django를 점검했다. 전체 20건의 patch·점수·usage를 코드로 대조했다. 오류/timeout 매핑은 합성 검사 6건으로 확인했다.

## 후속 설계

공통 프롬프트·실행·검증·제출 정책을 고정하고 다음 조건을 각각 비교한다.

| 조건 | S | U | E |
| --- | --- | --- | --- |
| B | S0 | U0 | E0 |
| S | S1 | U0 | E0 |
| U | S0 | U1 | E0 |
| E | S0 | U0 | E1 |

도구별 schema와 필수 사용 설명만 교체한다. 제한형 S0/U0/E0 선정과 구현이 다음 작업이다.
재현 스크립트 안내와 실행 도구의 정합성, 검색의 테스트 파일 제외 범위, 부분 수정 후 검증 누락을 우선 점검한다.
개발 10→20문제 후 노출 이력을 확인한 별도 50문제, 조건당 최소 5회 반복을 계획한다.
태스크·seed·순서를 실행 전에 고정하고 task 단위 paired bootstrap으로 불확실성을 제시한다.
2모델×50문제×4조건×5회×600초의 상한은 약 333시간이며 준비·채점은 별도다.

## 해석 범위

현재 결과는 이전에 노출된 5문제의 1회 실행이며 프롬프트·도구·제약이 함께 변경되었다.
개별 S/U/E 효과와 반복 안정성은 후속 비교에서 측정한다. 최종 평가 표본과 S0/U0/E0 설정은 선정 중이다.
실험 당시 자체 코드는 미커밋 상태여서 snapshot 해시로 식별한다. baseline serving 환경 누락분은 staged 환경으로 보완했으며,
실제 vLLM fingerprint 차이도 manifest에 기록했다. 교차 재현과 이번 제출 과정의 모델 재실행은 미실시다.
