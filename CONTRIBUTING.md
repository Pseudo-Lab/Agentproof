# AgentProof에 기여하기

처음 제출한다면 [파일럿 제출 안내](docs/SUBMISSION_GUIDE.md)를 따라 주세요.

- [복사용 실험 패키지](templates/experiment/README.md)
- [완성된 오프라인 연습 예시](experiments/E00-offline-example/CARD.md)
- [공통 실험 규칙](docs/EXPERIMENT_PROTOCOL.md)
- [시즌 성공 기준](docs/SUCCESS_CRITERIA.md)

매주 코드·설정·결과·의사결정 중 하나 이상을 작은 PR로 남깁니다.
실험 폴더는 `experiments/<experiment-id>-<slug>/`로 만들고 담당자는 카드에 적습니다.
다른 참여자의 재현 기록은 `reproductions/<experiment-id>-by-<runner-id>/`에 둡니다.
실험 ID는 기존 폴더와 열린 PR을 확인한 뒤 중복 없이 정하세요. E00은 연습용으로 예약합니다.

PR 제목: `[E01][pilot] 연구 주제` — 단계는 `pilot`, `results`, `reproduction`을 사용합니다.
설계만 먼저 논의할 때는 Draft PR을 열고 실행 전임을 명시하세요.
실험 코드·설정·작은 공개 로그·분석 코드는 함께 제출하고, 시크릿과 비공개 데이터는 제외합니다.
템플릿 원본은 개인 실험용으로 수정하지 말고 복사하세요.

리뷰는 성능 향상 여부가 아니라 비교의 타당성, 실행 근거, 재현 가능성, 주장과 로그의 일치를 봅니다.
유료 모델 API 재실행은 실행자와 예산을 합의한 뒤 진행합니다.
최종 통합은 squash merge를 사용합니다.
