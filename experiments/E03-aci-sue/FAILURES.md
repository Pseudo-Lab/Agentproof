# 실패 사례

전체 20건 중 실패 9건을 최종 패치·마지막 동작·공식 테스트로 확인했다.

| 모델·조건 | 문제 | 무엇을 하다가 실패했나 | 확인된 이유 |
| --- | --- | --- | --- |
| Gemma baseline | Astropy | RST 생성자와 출력 구분선을 고친 뒤 제출 | 읽기 경로가 여러 헤더 행을 처리하지 못해 `float64`를 데이터로 읽고 변환 오류 |
| Gemma staged | Astropy | 같은 출력 경로를 수정하고 diff 확인 후 제출 | 동일한 읽기 경로 누락 |
| Qwen staged | Astropy | 생성자에 header_rows만 추가, 기존 테스트 통과 후 제출 | 새 공식 header_rows 테스트에서 동일한 읽기 오류. 출력 구분선 처리도 그대로 남음 |
| Gemma baseline | Matplotlib | version_info 접근자를 추가하고 제출 | 공식 테스트가 호출하는 `_parse_to_version_info` 구현 누락 |
| Gemma staged | Matplotlib | 버전 문자열을 tuple로 바꾸는 접근자 작성 후 제출 | 동일한 parser 누락으로 4개 케이스 실패 |
| Qwen baseline | Matplotlib | `_version.version_tuple`을 노출하고 제출 | 동일한 parser 누락 |
| Qwen staged | Matplotlib | 재현 파일 생성→pytest 실행→직접 Python으로 실행하겠다는 응답 | 실제 호출은 `submit`; 제품 코드 수정 없이 재현 파일만 제출 |
| Qwen staged | Seaborn | 결측치 처리 누락을 찾고 재현 파일 생성→pytest 실행 | 직접 실행하겠다는 응답에서 `submit` 호출. 제품 코드 수정 없이 종료 |
| Qwen staged | Django | 검색과 코드 읽기를 진행 | 편집 전 `submit(paths=[])` 호출, 빈 패치로 종료 |

주요 패턴은 **부분 구현·검증 범위 누락 6건**, **작업 도중 제출 3건**이다.
모두 600초 전에 끝났다. Qwen staged의 짧은 평균 시간에는 이른 제출 실패가 포함된다.

Matplotlib의 공식 실패는 내부 helper 이름에 대한 테스트 요구도 포함하므로,
공개 기능을 얼마나 충족했는지와 공식 해결 여부를 함께 살펴볼 필요가 있다.
Qwen의 Matplotlib/Seaborn에서는 도구 설명의 Python 재현 안내와 pytest 중심 검증 인터페이스가 어긋났다.
이 불일치가 조기 제출에 영향을 주었는지는 후속 비교로 확인한다.
API가 반환한 `submit`과 실행된 동작은 일치했다. 모델 선택과 서버 parser의 기여를 구분할 raw 생성 토큰은 저장하지 않았다.

[사례별 근거](results/failure-evidence.json)에 trajectory 경로, 마지막 응답 인덱스·tool call,
공식 오류 발췌·원본 로그 SHA-256을 담았다. 개별 공식 report와 제출 patch는 각 run의 evidence에 있다.
