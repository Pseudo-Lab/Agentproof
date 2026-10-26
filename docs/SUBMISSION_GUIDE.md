# 파일럿 PR 제출 안내

이번 제출의 목적은 **작은 파일럿으로 실행 경로를 확인하고 최종 태스크·설계를 확정하는 것**입니다.
완성된 연구 결과나 성능 향상이 필수는 아닙니다. 실행하지 못했다면 Draft PR에 원인과 필요한 도움을 쓰세요.

PR 본문이 막막하면 [작성 예시](PILOT_PR_EXAMPLE.md)를 참고하세요.

## 1. 실험 패키지 복사

레포 루트에서 실행합니다. Python 3.10+와 Git이 필요하며 예시는 외부 패키지나 API 키를 쓰지 않습니다.
아래 E01과 slug는 기존 폴더·열린 PR과 겹치지 않는 값으로 바꾸세요.

```sh
git switch -c experiment/E01-my-question
cp -R templates/experiment experiments/E01-my-question
python3 experiments/E01-my-question/src/run.py --run-id smoke-001
python3 harness/summarize.py experiments/E01-my-question/results/pilot/smoke-001
```

이 명령은 **고정된 모의 응답**을 채점합니다. 연구 파일럿을 실행한 것으로 제출하면 안 됩니다.
먼저 [완성 예시](../experiments/E00-offline-example/CARD.md)로 파일 구성을 확인하세요.
동일한 run ID는 덮어쓰지 않습니다. 다시 실행할 때 새 ID를 쓰세요.

## 2. 내 연구로 교체

- `CARD.md`: 담당자, 질문·가설, 태스크 선정 이유, 최종 설계를 작성합니다.
- `data/tasks.json`: 실제 태스크나 데이터 확보 절차로 교체하고 버전·분할을 기록합니다.
- `configs/`: baseline과 intervention의 차이, 고정 조건, 반복 수·예산을 명시합니다.
- `src/run.py`: 모의 응답을 내 실행기로 교체합니다. 모델·도구 호출은 명시적으로 실행할 때만 발생하도록 만드세요.
- 채점기를 구현하고 정상·오답·실행 오류 사례에서 판정이 맞는지 확인합니다.
- `README.md`: 설치, 필요한 환경 변수 **이름**, 실행·분석 명령을 내 실험에 맞게 고칩니다.

실제 실행으로 교체할 때는 `execution_mode`, 모델 식별자와 로그 측정 방식을 함께 갱신하세요.
API 키는 `.env` 등 로컬 환경에 두고 커밋하지 마세요. 원문 응답·도구 인자에도 비밀이나 개인정보가 있는지 확인하세요.

## 3. 작은 파일럿 실행

파일럿 예산과 태스크·반복 수를 먼저 정하세요. 다음을 확인하고 카드에 근거를 적습니다.

- baseline이 너무 쉽거나 어려운지: 성공 수/전체 수를 쓰고 태스크별 분포도 확인
- 개입이 실제 적용되는지: 사용된 설정·프롬프트·도구 목록 등 공개 가능한 증거
- 채점·로그가 맞는지: 수동 확인한 사례와 오류·timeout 처리
- 시간·토큰·비용이 예상과 비슷한지: 미측정은 이유와 함께 표시
- 설계를 바꿨다면 무엇을 왜 바꿨는지: 파일럿 관찰과 최종 변경을 연결

파일럿을 본 뒤 고른 태스크로 평가했다는 사실도 기록하세요. 최종 효과를 주장할 때는 파일럿에서 튜닝에 쓰지 않은 평가 표본을 확보하세요.

## 4. PR에 포함할 파일

```text
experiments/E01-my-question/
  CARD.md
  README.md
  configs/baseline.json
  configs/intervention.json
  data/...
  src/...
  results/pilot/<run-id>/
    manifest.json
    trials.jsonl
    summary.json
```

작은 공개 로그는 Git에 포함합니다. 대용량·공개 제한 자료는 접근 위치, 버전·체크섬, 확보 방법과 공개 범위를 적으세요.
개인정보나 시크릿이 담긴 로그는 올리지 말고, 제거·가공한 범위를 명시하세요.
실제 구현의 상세 trace는 trial의 `evidence`에 상대 경로 또는 버전 고정 링크로 연결합니다.

```sh
git add experiments/E01-my-question
git diff --cached
# 내용과 민감정보를 직접 확인한 뒤 실행
git commit -m "[E01][pilot] 연구 주제"
git push -u origin experiment/E01-my-question
```

fork에서 작업하면 자신의 fork로 push한 뒤 `Pseudo-Lab/Agentproof:main`을 대상으로 PR을 엽니다.
제목은 `[E01][pilot] 연구 주제`, 본문은 자동으로 표시되는 PR 템플릿을 채우세요.

## 리뷰와 다음 단계

리뷰어는 제출 로그와 분석을 먼저 확인합니다. 유료 API를 자동으로 다시 실행하지 않습니다.
성능 하락·차이 없음도 유효한 결과입니다. 실행 누락·채점 오류·근거 없는 결론은 수정이 필요합니다.

본 실험은 같은 실험 폴더를 갱신하는 `[E01][results]` PR로 올립니다.
다른 참여자의 교차 재현은 `reproductions/E01-by-<runner-id>/`에 원본 commit·설정·실행 명령·결과·차이를 남기는 `[E01][reproduction]` PR로 제출합니다.
블로그는 고민과 해석을 설명하고, 수치·코드의 근거는 해당 실험의 commit 또는 PR로 연결하세요.
