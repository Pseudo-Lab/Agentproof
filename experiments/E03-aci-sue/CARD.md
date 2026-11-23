# E03 — 기존 인터페이스를 통한 코드 문맥·검증 피드백 보강

SLACT는 모델이 사용하는 bash 인터페이스와 기본 프롬프트를 유지하고,
환경에서 검색 문맥과 검증 결과를 보강한다. 자체 구현은 `tools/slcat/`에 있다.

## 방법

```text
모델의 기존 bash 명령
  ├─ grep 검색 → 원래 매칭 결과 → 주변 정의·코드 구조를 보강한 출력
  └─ 소스 수정 → 관련 공개 테스트 선택 → 백그라운드 실행
                                      → 이후 명령의 출력에 검증 결과 전달
```

| 구성 | 구현 | 기본 동작 |
|---|---|---|
| 검색 G | [grep_dispatch.py](tools/slcat/search-grep/grep_dispatch.py) | GNU grep 매칭을 유지하고 모델에게 직접 보이는 출력을 코드 구조에 맞춰 재구성 |
| 수정 감지 | [hook.sh](tools/slcat/edit-diff/hook.sh) · [edit_report.py](tools/slcat/edit-diff/edit_report.py) | 명령 전후 tracked 소스 변경을 감지 |
| 검증 V′ | [related_tests.py](tools/slcat/edit-diff/related_tests.py) | 수정 모듈과 import·경로가 관련된 공개 테스트를 최대 3개 선택하고 실행 |
| 결과 전달 | 같은 hook과 검증 모듈 | 완료된 결과를 이후 명령의 출력에 추가; 제출·패치 회수 출력에는 삽입하지 않음 |
| 연결 설정 | [aci-slcat.yaml](configs/aci-slcat.yaml) | 기존 도구·프롬프트를 유지하면서 G와 V′ 활성화 |

모델이 별도 도구를 선택하거나 새 호출 문법을 익힐 필요가 없는 전달 방식을 목표로 한다.
테스트 실행 상태, 기준 코드와의 비교 가능 여부, 코드 버전 등을 구분해 전달한다.
관련 테스트 일부의 성공이 이슈 해결이나 전체 회귀 부재를 보장하지는 않는다.

현재 공개한 코드는 로컬 작업 버전이다. 초기 BF16 100문제 실행 당시 코드와 동일한
스냅샷이라고 주장하지 않는다. 이번 폴더 정리에서는 모델 추론이나 벤치마크를 재실행하지 않았다.

## 도구별 소유 관계

- [tools/swe-agent/](tools/swe-agent/): SWE-agent의 창 단위 읽기·lint 편집 도구와 실행 래퍼.
- [tools/codestruct/](tools/codestruct/): CodeStruct 읽기·편집 도구, UTF-8 수정 패치와 stdin 어댑터.
- [tools/slcat/](tools/slcat/): 자체 검색 보강과 수정 후 검증·피드백. AutoCodeRover 파싱 helper를 고정 버전으로 재사용한다.

비교 조건은 같은 mini 실행 루프에 각각의 도구를 연결한다. 전체 SWE-agent 또는
CodeStruct 시스템과의 비교가 아니며, 도구를 제공하는 조건은 해당 사용 지침도 포함한다.
Base와 SLACT의 프롬프트·모델 설정 일치는 개발용 검사에서 확인한다.

실행 입력은 [SWE-bench Verified 고정100](data/selection.json)이다.
설치·실행·채점 방법은 [README](README.md)에 있다.

## 과거 S/U/E 파일럿 기록

아래는 2026-10-26의 **SWE-bench Lite 5문제** 실험이다. 당시 변형은 셸을 없애고
별도 named tool과 S→U→E 단계 정책을 사용했다. 위 SLACT 및 현재 고정100 결과와 구분한다.

| 모델·당시 조건 | 해결 | 평균 시간 | 입력 토큰 합 | 출력 토큰 합 | 요청 수 |
|---|---:|---:|---:|---:|---:|
| Gemma baseline | 3/5 | 425.8초 | 1,992,385 | 43,794 | 147 |
| Gemma S+U+E | 3/5 | 400.8초 | 2,038,583 | 40,239 | 147 |
| Qwen baseline | 4/5 | 337.0초 | 3,293,704 | 39,565 | 206 |
| Qwen S+U+E | 1/5 | 229.2초 | 4,672,640 | 23,740 | 139 |

모델별 5문제 × 2조건 × 1회, 총 20건이다. 인터페이스·프롬프트·오류 처리를 함께
바꾼 비교이며 개별 도구 효과를 분리하지 못했다. Qwen의 시간 감소에는 조기 제출 실패가 포함된다.
[당시 실패 사례](FAILURES.md)는 기록으로 남겼다. 당시 runner·설정·결과·원자료는 로컬에 보관한다.
