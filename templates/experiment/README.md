# 실험 실행 안내

복사한 뒤 이 문서를 내 실험의 설치·실행 안내로 바꾸세요.
공통 절차는 [제출 안내](../../docs/SUBMISSION_GUIDE.md), 설계·결론은 [CARD.md](CARD.md)에 적습니다.

## 기본 예시: API 없는 모의 실행

Python 3.10+ 표준 라이브러리만 사용합니다. 레포 루트에서 실행하세요.
아래 경로는 복사한 실험 경로로 바꿉니다.

```sh
python3 templates/experiment/src/run.py --run-id smoke-001
python3 harness/summarize.py templates/experiment/results/pilot/smoke-001
```

3개 태스크 × 2개 조건 × 5회 = 30개 모의 시도를 만듭니다.
설정에 들어 있는 고정 응답을 정답과 비교하는 연습이며 모델·도구를 호출하지 않습니다.
baseline/intervention 응답 차이는 사람이 설정한 fixture입니다. 실제 개입 효과를 보여주지 않습니다.
모의 실행이므로 토큰·비용은 null과 이유로 남기고, latency는 로컬 채점 시간만 측정합니다.

결과는 이 실험의 `results/pilot/<run-id>/`에 저장됩니다.
기존 실행 폴더는 덮어쓰지 않습니다. 다른 run ID를 쓰세요.
`harness/summarize.py`는 로그를 검증한 뒤 요약을 표준 출력으로 보냅니다. 저장된 summary와 비교할 수 있습니다.

## 실제 연구로 바꿀 부분

- `configs/*.json`: 조건·모델·반복·예산
- `data/tasks.json`: 실제 평가 태스크와 정답, 출처·사용 권한
- `src/run.py`: 모델/에이전트 실행, 개입 적용 증거, 채점과 실패 처리
- 실제 모델 호출 여부·환경 변수 이름·예상 비용·실행 명령을 이 README에 명시
- sampling·seed·의존성 버전과 재현 절차를 추가

현재 예시는 재시도 없이 조건별·태스크별·반복별 순서대로 실행합니다.
실제 연구에서 순서를 바꾸면 정책과 로그를 기록하세요. 예산 상한은 실행기에 별도로 구현해야 합니다.
