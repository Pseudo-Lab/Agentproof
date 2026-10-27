# E03 — S/U/E 도구 인터페이스와 코딩 에이전트의 효율

**mini-swe-agent 기반으로 검색(S)·읽기(U)·편집(E) 도구의 해결률과 효율을 비교한다.**

- 담당자: [muuty](https://github.com/muuty)
- 단계: 실제 모델 파일럿. 실행 2026-10-26 UTC, 제출 정리 2026-10-27.
- 질문: 기존 Search / Understanding / Editing 도구를 제공하고 사용 경로를 제한하면 해결률과 시간·토큰 사용이 어떻게 달라지는가?
- 가설: 구조화된 검색·읽기·편집은 탐색 낭비를 줄일 수 있다. 이번에는 도구 사용과 에이전트 연동부터 점검했다.

## 비교

두 조건은 **mini-swe-agent의 기본값(Baseline)**과 **named tool로 교체한 변형(S+U+E)**이다.
Baseline은 mini의 bash 인터페이스를 거의 그대로 쓰고(seed·deadline만 추가), S+U+E는
에이전트 종류·프롬프트·도구·호출·오류 처리를 함께 바꾼 묶음이다. 따라서 개별 요소 비교가
아니라 인터페이스 묶음 비교다(`intervention.json`의 `comparison` 필드에 동일하게 명시).

| 항목 | Baseline (mini 기본값) | S+U+E (변형) |
| --- | --- | --- |
| 설정 | [baseline.json](configs/baseline.json) | [intervention.json](configs/intervention.json) |
| 에이전트 | bash 에이전트 (셸 도구 1개, 코드상 `BudgetAgent`) | ACI 에이전트 (named tool 집합, 코드상 `StagedAgent`) |
| 도구 호출 방식 | 셸 명령을 bash 도구로 자유 실행 | 셸 없이 이름이 정해진 도구만 JSON 인자로 호출 |
| S (검색) | 셸 명령(grep/find 등) | AutoCodeRover AST 검색 API 8종 |
| U (읽기) | 셸 명령(cat/sed 등) | CodeStruct `readCode` |
| E (편집) | 셸 명령(sed/python 등) | `str_replace` · `editCode` · `create_file` |
| 전환 | 자유 선택 | 초기 S→U→E, 이후 복귀 가능 |
| 검증·제출 | 셸 테스트 실행 후 `patch.txt` 수동 작성 | `run_tests`(pytest/Django)·`view_diff`·`submit` |
| 호출 수 | 응답당 복수 허용(`parallel_tool_calls: true`) | 응답당 하나(`parallel_tool_calls: false`) |
| 프롬프트 | bash 지침 | 단계·도구·검증·제출 지침 |
| 오류 처리 | format error 상한 3, API retry 억제 | 상한 0, deadline 내 원본 retry |

### named tool이란

Baseline에서는 모델이 `bash` 도구 하나로 모든 작업(검색·읽기·편집·테스트)을 셸 명령으로
자유롭게 수행한다. S+U+E에서는 셸 도구가 제거되고, **이름과 인자 스키마가 고정된 전용 도구**
(아래 S/U/E 도구 + `run_tests`·`view_diff`·`submit`)만 노출된다. 모델은 응답마다 이 중 정확히
하나를 JSON 인자로 호출한다. 도구 스키마는 [intervention-tools.json](configs/intervention-tools.json)에 있다.

### S/U/E 도구 상세

- **S — Search (검색).** AutoCodeRover의 Python AST 검색 백엔드를 재사용한 8종 API다.
  `search_class`(클래스 시그니처), `search_class_in_file`, `search_method`(함수/메서드 본문),
  `search_method_in_file`, `search_method_in_class`, `search_code`(코드 조각), `search_code_in_file`,
  `get_code_around_line`(1-based 라인 주변 코드). 인덱싱된 Python 소스만 검색하며 테스트·파싱 불가
  파일은 upstream 기준으로 제외된다. 인덱스는 시작 전 준비되고 편집 후 갱신된다.
- **U — Understanding (읽기).** CodeStruct의 `readCode PATH [--selector NAME] [--line-start N --line-end M]`.
  10,000자 미만 파일은 전체 내용을, 그 이상은 시그니처만 반환한다. `--selector`로 함수·클래스 단위
  (`is_fits`, `Calculator.add` 등), 라인 범위로 정확한 구간을 요청한다. CodeStruct의 UTF-8 위치
  수정 패치를 적용했다(tools/*/patches에 기록).
- **E — Editing (편집).** `str_replace PATH OLD NEW`(정확히 1회 일치하는 작은 변경, 5줄 미만 권장),
  `editCode PATH OP SELECTOR [--replacement CODE]`(CodeStruct AST 편집: `replace_node`/`insert_node`/
  `delete_node`로 함수·클래스 단위 수정), `create_file PATH [CONTENT]`(새 파일 생성). 이 원본 CLI들은
  오류가 있어도 exit code 0을 반환할 수 있어 결과·diff를 직접 확인하도록 안내한다.

### 구현 코드 위치

S/U/E 인터페이스는 두 층으로 나뉜다. **도구 래퍼**는 컨테이너 PATH에 설치되는 CLI이고,
**ACI 에이전트 엔진**은 셸을 제거하고 named tool 호출·단계 전환·검증/제출을 담당한다.

| 구성 | 경로 |
| --- | --- |
| S 도구 (AutoCodeRover 8 API) | [tools/search/](tools/search/) (`bin/`, `search_dispatch.py`, upstream `auto-code-rover`) |
| U 도구 (CodeStruct readCode) | [tools/understanding/codestruct/](tools/understanding/codestruct/) (`bin/readCode`, upstream `CodeStruct`) |
| E 도구 (str_replace·editCode·create_file) | [tools/editing/](tools/editing/) (`bin/`, upstream `lib`) |
| 도구 설치 스크립트 | 각 도구의 `install.sh` (컨테이너 기동 시 PATH에 링크) |
| 도구 JSON 스키마 | [configs/intervention-tools.json](configs/intervention-tools.json) |
| ACI 에이전트 엔진 (named tool, 단계 전환) | [src/minisweagent/run/benchmarks/aci_staged.py](src/minisweagent/run/benchmarks/aci_staged.py) — 코드상 클래스명은 `StagedModel`/`StagedAgent` |
| Baseline 엔진 (bash, deadline) | [src/minisweagent/run/benchmarks/aci.py](src/minisweagent/run/benchmarks/aci.py) — `DeadlineModel`/`BudgetAgent` |
| 엔진 실행 config | [src/minisweagent/config/extra/aci-staged.yaml](src/minisweagent/config/extra/aci-staged.yaml), `aci-sue.yaml`, `aci-common.yaml` |

ACI 에이전트 엔진(`aci_staged.py`)과 실행 config(`aci-staged.yaml`)는 공개 스냅샷이 baseline 기준으로
체크아웃되어 처음 번들에서 빠졌다가, 실험에 사용한 staged run의 소스 감사본(before.tar.gz)에서
sha256이 일치하는 바이트 그대로 복원했다(`results/provenance/source-code.json`에 해시 기록).

mini 2.4.6, 공식 SWE-bench 4.1.0과 기존 도구를 사용했다. [원본 commit](configs/upstreams.lock.json),
[mini 소스](src/minisweagent/), [도구 schema](configs/intervention-tools.json)를 포함한다.

- 데이터: SWE-bench Lite test revision `6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`의 [기존 점검용 5문제](data/tasks.json).
- 표본: 모델별 5문제 × 2조건 × 1회 = 총 20건. 앞선 실험에서 사용한 문제다.
- 예산: 문제당 600초, 요청·step 상한 없음. 준비·인덱싱·공식 채점은 별도. 종료 후 패치 회수 최대 30초.
- 모델: Gemma-4-31B-it / Qwen3.5-27B, seed 42, thinking 활성화, 모델별 1 worker. revision과 sampling은 manifest에 저장했다.
- 순서: 기존 bash baseline 배치와 이후 audited S+U+E 배치를 비교했다. S+U+E는 Gemma→Qwen 순서다.
- 채점: 제출을 마친 뒤 공식 SWE-bench evaluator 사용. 빈 패치도 분모에 포함한다.

## 결과

| 모델·조건 | 해결 | 평균 시간 | 입력 토큰 합 | 출력 토큰 합 | 요청 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma baseline | 3/5 | 425.8초 | 1,992,385 | 43,794 | 147 |
| Gemma S+U+E | 3/5 | 400.8초 | 2,038,583 | 40,239 | 147 |
| Qwen baseline | 4/5 | 337.0초 | 3,293,704 | 39,565 | 206 |
| Qwen S+U+E | 1/5 | 229.2초 | 4,672,640 | 23,740 | 139 |

- Gemma는 같은 3문제를 해결했다. Qwen은 빈 패치 1건과 재현 파일만 제출한 2건에서 일찍 종료했다.
- S+U+E 10건 모두 S/U를 사용했고, 제품 코드 수정은 7건이었다. [실패 9건 분석](FAILURES.md)
- Agent timeout·공식 채점 실행 오류는 0건. 도구 오류는 trajectory에 보존했다.
- 시간은 native 정수 초, 토큰은 저장된 API usage 합이다. GPU 비용은 미측정으로 `null` 처리했다.
- [Gemma 기록](results/pilot/E03-gemma31b-historical-pilot5/manifest.json), [Qwen 기록](results/pilot/E03-qwen27b-historical-pilot5/manifest.json): 각각 manifest/trials/summary와 원본 형식 evidence를 포함한다.
- 채점 확인: 성공한 Xarray, 실패한 Astropy, 빈 패치 Django를 점검했다. 전체 20건의 patch·점수·usage를 코드로 대조했다. 오류/timeout 매핑은 합성 검사 6건으로 확인했다.

## 후속 설계

이번 파일럿은 인터페이스를 묶음으로 바꿨으므로 개별 S·U·E의 효과를 분리하지 못한다.
후속에서는 공통 프롬프트·실행·검증·제출 정책을 고정하고, 기준 조건에서 S·U·E 중
**하나씩만** named tool로 교체해 각 요소의 효과를 분리한다.

| 조건 | S | U | E | 설명 |
| --- | --- | --- | --- | --- |
| B | 기준 | 기준 | 기준 | 모든 요소가 제한형 기준 도구 |
| S | named | 기준 | 기준 | 검색만 교체 |
| U | 기준 | named | 기준 | 읽기만 교체 |
| E | 기준 | 기준 | named | 편집만 교체 |

조합 효과가 필요하면 같은 방식으로 `S+E` 등 두 요소를 동시에 교체해 추가 비교한다.
각 조건은 도구 schema와 필수 사용 설명만 바꾸고 나머지는 동일하게 둔다.
제한형 기준 도구(B의 S·U·E) 선정과 구현이 다음 작업이다.
재현 스크립트 안내와 실행 도구의 정합성, 검색의 테스트 파일 제외 범위, 부분 수정 후 검증 누락을 우선 점검한다.
개발 10→20문제 후 노출 이력을 확인한 별도 50문제, 조건당 최소 5회 반복을 계획한다.
태스크·seed·순서를 실행 전에 고정하고 task 단위 paired bootstrap으로 불확실성을 제시한다.
2모델×50문제×4조건×5회×600초의 상한은 약 333시간이며 준비·채점은 별도다.
