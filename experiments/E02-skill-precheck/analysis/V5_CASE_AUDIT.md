# v5 산출물 전이와 궤적 점검

2026-11-09. 아래는 원 trace와 before_post/output을 직접 대조한 탐색적 사례 검토다. 첫 입력 seed 2026111001의 세 과제 × V/P 6건을 고정 표본으로 골랐고, 산출물 분류가 바뀐 사례는 한 건 모두 확인했다. 좋은 사례만 고르지 않았다. 모델 의도나 앵커링의 인과 판정은 하지 않는다.

## 고정 표본

| Trial | 첫 완료 → 최종 | 사후 단계의 도구 호출 |
|---|---|---|
| graph-E1-L3-V-i2026111001 | 스킬 호환 오답 유지 | run_python 1회, 입력·출력 비교 코드 |
| graph-E1-L3-P-i2026111001 | 정답 유지 | run_python 1회, 입력·출력 비교 코드 |
| csv-E1-L3-V-i2026111001 | 스킬 호환 오답 유지 | output/normalized.csv read_file 1회 |
| csv-E1-L3-P-i2026111001 | 스킬 호환 오답 유지 | output/normalized.csv read_file 1회 |
| events-E1-L3-V-i2026111001 | 스킬 호환 오답 유지 | output/daily.csv read_file 1회 |
| events-E1-L3-P-i2026111001 | 스킬 호환 오답 유지 | 도구 호출 없이 완료 |

이 표의 경로들은 해당 trial `trace.json`의 developer 사후 메시지 이후 function_call에서 확인했다. csv의 두 사례는 그 단계에서 출처 해석을 정하는 meta/source.json을 읽지 않았다. 이전 단계에서 본 내용을 내부적으로 고려했는지는 도구 호출만으로 판정하지 않는다.

특히 events P 첫 seed의 전체 trace에는 작업 공간 목록, 계약, 입력 CSV, UTC 날짜 집계 코드, 산출물 열람이 있으나 config/report.json 내용을 읽는 호출은 없다. 목록에 파일이 보였다는 것과 그 내용을 대조했다는 것을 구분한다. 해당 run_python 코드는 os.walk 목록 확인과 CSV 집계였으며 설정 파일 내용은 읽지 않았다.

## 분류가 바뀐 전 사례

`graph-E1-L3-V-i2026111004` 한 건이었다.

- 입력 nodes.csv에는 L1과 L2의 speaker가 Traveler로 들어 있다(trace items[8–9]).
- 첫 산출물 write_file(items[13])에는 원본 speaker 값과 from/to 간선 키가 있다. E1에는 틀리지만 전체 E0 채점은 통과했다.
- 사후 메시지 뒤 write_file(items[18])는 from/to를 유지하면서 L2의 speaker만 빈 문자열로 바꿨다(L1은 Traveler를 유지).
- 최종 산출물은 E1과 E0 채점 모두 실패하고 `nodes_mismatch`가 됐다.

즉 오답이 정답으로 교정된 사례가 아니라 스킬 호환 오답에 다른 오류가 추가된 사례다. 원래 정답이었던 실행이 틀린 답으로 바뀌었다고 표현하지 않는다.

## 저장 좌표와 범위

모든 경로의 기준은 `results/v5/report-v5-001/traces/<trial>/`다. 첫 산출물은 before_post/, 마지막 산출물은 output/, 도구 요청·반환은 trace.json이다. 전체 180 trial의 두 시점 산출물을 재채점한 `artifact_audit.json`은 1,800개 대조에서 불일치 0건이다. 이는 저장·집계의 일관성 검사이며, 독립적인 두 번째 채점기를 구축했다는 뜻은 아니다.
