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

- 데이터: SWE-bench Lite test revision `6ec7bb89b9342f664a54a6e0a6ea6501d3437cc2`의 [기존 점검용 5문제](data/tasks.json). 이 파일럿은 기존 노출된 Lite 문제를 재사용했으므로, SWE-bench Verified 기준으로 보고되는 mini-swe-agent 공식 수치와 직접 비교하지 않는다(후속 설계에서 Verified Mini로 전환).
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

### dev10 bring-up 결과와 S/U/E 가설

후속 벤치마크(Verified Mini)에서 10문제(5 django + 5 sphinx, seed 42) dev subset으로 baseline을
먼저 돌렸다. Gemma baseline은 **5/10 resolved**였고, 미해결 5건 중 4건이 `TimeExceeded`(600초 소진)였다.
실패 trajectory를 명령 단위로 분류하면 탐색/읽기(shell grep·find·cat·sed)가 압도적이다.

| 사례 | 결과 | 명령 수 | 탐색/읽기 비율 | 편집 |
| --- | --- | ---: | ---: | ---: |
| sphinx-7757 | TimeExceeded | 51 | 82% | 0 |
| sphinx-9461 | TimeExceeded | 56 | 89% | 0 |
| django-11880 | resolved | 26 | 69% | 제출까지 도달 |

즉 baseline 실패의 주된 형태는 "구조 없는 탐색의 폭주"다. 자유 shell에서 관련 코드를 못 찾고
grep/find/cat을 수십 번 반복하다 편집·검증에 도달하지 못한 채 시간이 끝난다. 이것이 S/U/E
인터페이스의 개입 가설을 구체화한다.

- **S (구조화 검색)**: AST 기반 심볼 검색으로 "관련 파일·심볼 찾기"의 반복을 줄여 탐색 시간을 단축한다.
  가설: TimeExceeded 비율이 낮아지고, 성공 trial의 탐색 명령 수가 감소한다.
- **U (구조화 읽기)**: 시그니처 우선 읽기로 거대 파일을 통째로 읽는 낭비를 줄인다.
  가설: 입력 토큰 폭증(대형 파일 덤프) 사례가 줄고, 필요한 맥락에 더 빨리 도달한다.
- **E (구조화 편집)**: 함수·클래스 단위 편집으로 shell rewrite의 실수(부분 수정·검증 누락)를 줄인다.
  가설: 제출했으나 틀린 패치(django-12406 유형)가 줄어든다.

### 평가 지표 (성능 = localization)

최종 해결률(resolved)은 편집·검증·종료 정책 등 S/U/E 밖의 요인에 크게 좌우되므로, S/U의 성능은
**탐색 과정에서의 line-level fault localization**으로 측정한다. 기존 FL 연구는 최종 출력한 위치 목록을
file/function/line 단위 Hit@k·Recall로 채점하지만, 여기서는 에이전트가 **탐색 중 실제로 본 코드**를 채점한다.

- **정답 줄**: gold patch가 바꾸는 base commit의 줄(삭제·수정 줄). 순수 삽입은 삽입 지점의 양옆 base 줄.
- **본 줄**: tool 관찰(observation)에 base 파일의 해당 줄 텍스트가 그대로 나타난 경우만 센다. mini의 출력
  절단(앞뒤 5000자)을 반영하므로, 긴 파일 `cat`은 생략된 가운데 부분을 본 것으로 치지 않는다. 줄 번호가
  있는 출력(grep -n, nl, get_code_around_line, traceback)은 번호와 텍스트가 base와 일치할 때만 인정한다.
- **located / steps-to-locate**: 정답 줄이 처음 보인 tool call과 그 순번.
- **lines-to-locate**: 그때까지 본 소스 줄 수(반복 포함) — 탐색 비용.
- **hit precision**: 첫 적중 관찰에서 정답 줄 / 그 관찰의 소스 줄 — 조준 정밀도.
- **cumulative precision**: 첫 적중의 정답 줄 / lines-to-locate — 탐색 효율.
- **location coverage**: 탐색 전체에서 본 gold 변경 블록 / 전체 블록 — 다중 위치 문제용.
- 보조: 도구 사용 건강성(인자오류·라인폴백), resolved·TimeExceeded.

고정 줄 수 기준(예: N줄 이하) 없이 비율로 정밀도와 비용을 함께 본다. 구현은
[src/localization_metrics.py](src/localization_metrics.py)이며, base 파일은 SWE-bench instance 이미지에서
`git archive <base_commit>`으로 읽는다. 실행할 때마다 패치의 문맥·삭제 줄을 base 파일과 대조한다(dev10: 231줄
전부 일치). 실패는 유형별로 귀인한다: localization 실패 / 오답 편집 / 과탐색 시간초과 / 빈 패치.

### S 조건 실행과 도구 인터페이스 개선 (dev10)

같은 10문제에 S(AutoCodeRover 검색)를 켜고 돌렸다. 검색 호출 97건의 건강성을 보면
**정상 46%, 인자오류 15%, 라인번호 폴백 34%**였다. 모델이 `search_method NAME FILE`처럼 1인자 API에
파일 경로를 넘겨 argparse가 실패하면, 검색을 포기하고 `get_code_around_line`으로 라인을 추측해
읽는 폴백이 반복됐다.

이를 근거로 dispatch 래퍼(원본 백엔드는 불변)에 두 ACI 개선을 넣었다.

1. **관대한 인자 라우팅**: 1인자 검색에 파일 경로가 붙으면 `*_in_file` API로 자동 라우팅한다.
2. **exact→fuzzy 매칭**: 정확 일치가 없으면 인덱스에서 부분·근접(difflib) 심볼 후보를 제시한다.

개선 S'는 검색 호출 86건에서 **인자오류 15%→1%**, 자동 라우팅 13건, fuzzy 제안 2건을 기록했다.
line-level FL로 채점하면 세 조건 모두 10/10에서 정답 줄을 보므로 도달 여부는 변별력이 없고,
차이는 **비용과 정밀도**에서 난다.

| 조건 | located | steps(중앙값) | lines-to-locate(중앙값) | hit prec | cumulative prec | coverage | 인자오류 | (참고) resolved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B (bash) | 10/10 | 4.5 | 190 | 0.063 | 0.029 | 0.90 | — | 5/10 |
| S (원본) | 10/10 | 3.0 | 154 | 0.071 | 0.032 | 0.88 | 15% | 5/10 |
| **S' (개선)** | 10/10 | 4.0 | **43** | **0.079** | **0.052** | 0.90 | **1%** | 5/10 |

S'는 정답 줄에 닿기까지 읽는 소스 줄의 중앙값을 190→43으로 줄이고 탐색 효율(cumulative precision)을
1.8배 높였다. 다만 문제별로는 B 대비 줄 수가 줄어든 문제 4건(django-12039, sphinx-10673·11510·9461),
늘어난 문제 4건, 같은 문제 2건으로 갈리며 총합은 1,996→1,627줄(−18%)이다. 10문제·1회라 방향만 확인한
수준이다. 출력 절단 반영의 효과도 컸다: django-11790 B의 `cat forms.py`(435줄)는 292줄만 보여 줘 194행
(gold)이 생략 구간에 있었고, 실제 첫 적중은 4번째 `sed -n '163,210p'`였다. 상세는
`results/dev/localization-metrics.json`.

resolved는 셋 다 5/10이다. 해결 문제 구성은 이동했다:
S'는 sphinx-7757을 새로 해결하고, baseline이 풀던 django-11790·sphinx-10673을 놓쳤다. 이 두 손실은
**S 검색의 결함이 아니다**:

- **django-11790 (오답 편집)**: S'도 gold 파일·심볼을 정확히 찾았으나, 모델이 `widget.attrs['maxlength']`
  직접 할당(정답) 대신 `widget_attrs()` 호출이라는 **틀린 편집 전략**을 택해 테스트 실패. 편집(E)의 문제.
- **sphinx-10673 (과탐색 시간초과)**: 인자오류가 사라져 검색이 매끄러워지자 오히려 탐색을 27회까지
  반복하며 편집↔재탐색을 맴돌다 제출 타이밍을 놓쳐 600초 초과. 종료 정책의 문제.

즉 S 개선은 상류(탐색)를 고쳐 하류의 다른 병목(편집 판단, 종료 정책)을 드러냈다.

관찰과 다음 과제:

- 인터페이스 품질(인자오류)은 명확히 개선됐고 정답 줄까지 읽는 비용도 줄었지만, resolved 총점은 그대로다.
  S 도구 강제(tool_first)가 쉬운 문제의 작동하던 bash 흐름을 방해하는 **양날의 검** 패턴이 보인다.
- 라인번호 폴백 34%는 S'에서도 그대로다. 이는 인자 문제가 아니라 "심볼 검색보다 라인 읽기를 선호"하는
  행동이며, 프롬프트·정책으로 유도할 다음 과제다.
- 10문제×1회는 ±2 이동이 노이즈인지 실제 효과인지 구분하기에 표본이 너무 작다. 조건당 5회 반복과
  전체 Verified Mini 50문제 평가가 필요하다는 점이 이 dev 결과로 재확인된다.
- 상세: `results/dev/comparison-S-vs-baseline.json`, 개선 dispatch는 `results/dev/search_dispatch.improved.py`(파일럿 원본은 불변).

데이터셋은 이번 파일럿의 SWE-bench Lite에서 **SWE-bench Verified Mini로 전환한다.**
mini-swe-agent 공식 결과가 SWE-bench Verified 기준으로 보고되므로, 같은 계열 벤치마크를 써야
공식 수치와 비교할 수 있다. Verified Mini는 원본 SWE-bench Verified에서 무작위로 고른 50문제
subset으로, 평가 비용이 낮아 조건당 반복 실행에 적합하다. 노출 이력을 확인한 뒤 개발 10→20문제로
파이프라인을 점검하고, 평가는 Verified Mini 50문제에 조건당 최소 5회 반복한다.
태스크·seed·순서를 실행 전에 고정하고 task 단위 paired bootstrap으로 불확실성을 제시한다.
2모델×50문제×4조건×5회×600초의 상한은 약 333시간이며 준비·채점은 별도다.

출처와 참고:
- Verified Mini subset (50문제): Marius Hobbhahn, HuggingFace `MariusHobbhahn/swe-bench-verified-mini`. 전용 논문은 없다.
- 리더보드: Princeton HAL (`princeton-pli/hal-harness`).
- SWE-bench Verified: OpenAI, "Introducing SWE-bench Verified" (원본 Verified 500문제의 상위 집합).
- 원 논문: Jimenez et al., "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" (2023), arXiv:2310.06770.

관련 연구: Tripathy et al., "SWEnergy: An Empirical Study on Energy Efficiency in Agentic Issue
Resolution Frameworks with SLMs" (AGENT 2026, ICSE 2026 workshop; arXiv:2512.09543)는 SWE-Agent,
OpenHands, Mini SWE Agent, AutoCodeRover 네 프레임워크를 Gemma-3 4B·Qwen-3 1.7B로 SWE-bench Verified
Mini에서 비교하며 에너지·시간·토큰·메모리를 측정했다. 같은 벤치마크·프레임워크 계열을 다루므로 본 연구의
직접 비교 대상이다. 다만 SWEnergy가 프레임워크 간 에너지 효율을 비교하는 데 비해, 본 연구는 동일 프레임워크
(mini-swe-agent) 안에서 S·U·E 인터페이스 요소를 각각 분리해 효과를 측정하는 점이 다르다.
