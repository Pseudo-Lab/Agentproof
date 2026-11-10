# v5 사후 단계 Python 전수 검토

2026-11-10. 추가 API 호출 없이 저장된 trace를 검토했다. 사후 검증 조건 V/P의 60 trial(E0/E1 각 30)에 대해, 사후 developer 메시지 이후의 모든 도구 요청·반환을 집계했다. Python 호출 15개는 코드를 전부 읽고 접근 경로와 실행 결과를 확인했다. 파일명 검색에 걸리지 않았다는 이유만으로 근거 조회가 없다고 판정하지 않았다.

| Trial | 사후 Python이 읽은 파일 | 확인한 내용 |
|---|---|---|
| graph-E1-L3-V-i2026111001 | input/nodes.csv, input/edges.csv, output/graph.json | 노드·간선 수/값과 from/to 키 |
| graph-E1-L3-P-i2026111001 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 source/target 키 |
| events-E1-L3-V-i2026111002 | input/events.csv | UTC 날짜별 재집계 |
| graph-E1-L3-V-i2026111002 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 from/to 키 |
| graph-E0-L3-P-i2026111002 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 from/to 키 |
| csv-E0-L3-P-i2026111003 | input/measurements.csv, output/normalized.csv | 쉼표를 소수점으로 파싱한 값 일치 |
| events-E0-L3-P-i2026111003 | input/events.csv, output/daily.csv | UTC 날짜 재집계와 출력 비교 |
| graph-E1-L3-P-i2026111003 | output/graph.json | 객체 구조·개수·source/target 키 |
| graph-E0-L3-P-i2026111003 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 from/to 키 |
| events-E1-L3-P-i2026111004 | input/events.csv, output/daily.csv | UTC 날짜 재집계와 출력 비교 |
| events-E0-L3-P-i2026111004 | input/events.csv, output/daily.csv | UTC 날짜 재집계와 출력 비교 |
| graph-E0-L3-P-i2026111004 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 from/to 키 |
| graph-E1-L3-P-i2026111005 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 source/target 키 |
| events-E1-L3-P-i2026111005 | input/events.csv, output/daily.csv | UTC 날짜 재집계와 출력 비교 |
| graph-E0-L3-P-i2026111005 | input/nodes.csv, input/edges.csv, output/graph.json | 입력·출력 보존과 from/to 키 |

15개 모두 `exit=0`이었다. 정상 종료는 검증의 타당성을 뜻하지 않는다. 예를 들어 E1 events의 UTC 재집계는 처음의 잘못된 전제를 그대로 재사용하면서 일관성만 확인했다.

이 코드들에는 외부 프로그램 실행, 동적 코드 실행, 환경 근거 파일을 찾아 읽는 경로가 없었다. 다른 사후 read_file 호출은 모두 output/ 아래를 읽었다. 따라서 **기록된 사후 단계에서 환경 근거의 새 조회는 없었다**고 기술할 수 있다. 다만 사전에 읽은 정보를 내부적으로 활용했는지는 관찰하지 못하며, 조회가 없다는 사실만으로 생각하지 않았다고 단정하지 않는다.

자료: `results/v5/report-v5-001/traces/<trial>/trace.json`. 각 Python 코드·반환 전문과 trial별 행동 집계는 `analysis/v5_sensitivity.json`에 보존했다. 이 검토는 사후 탐색 분석이며 원래 등록한 주요 비교를 대체하지 않는다.
