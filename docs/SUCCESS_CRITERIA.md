# AgentProof Success Criteria (S13)

시즌 프레임: **16주** / 실활동: **14주**(활동 12주 + 방학 2주) / W16: 릴리스 후 회고·비동기 정리

## 개인 (Runner)
- Research Question 1개 확정 (W4 Proposal Day)
- Experiment Card ≥ 1 (최종), 중간 업데이트 권장
- baseline vs intervention **최소 5회** 반복 (초기 점검의 출발점이며 본 실험 표본의 충분성을 보장하지 않음; 태스크 수·반복 수·seed 지원과 정책을 구분해 문서화)
- cross-reproduction **1회** (다른 Runner 실험)
- 매주 GitHub에 코드·설정·결과·의사결정 중 ≥1 기록

## 공통 (팀)
- 공통 task suite ≥ 3
- 공용 evaluation harness (설치·실행 README 포함)
- Experiment Board (Runner 결과 비교)
- 시도별 로그 규격 준수율 100% (성공 상태·토큰·비용 및 미측정 이유), 요약에는 정의된 reliability 포함
- OSS v1.0: MIT, reproducible runbook, sample Experiment Cards

## v1.0 Acceptance Checklist
- [ ] `README`로 신규 기여자가 baseline 실험 1회 재현 가능
- [ ] Experiment Card 템플릿 + 예시 ≥ 1
- [ ] Board에 Runner별 결과 요약
- [ ] cost/token 필드 및 reliability 요약 누락 0 (미측정은 null과 이유, 모의 결과는 실제 연구에서 제외)
- [ ] Grand Gathering 발표 자료 또는 통합 리포트

제출 규칙·측정 정의: [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md).
