# AgentProof

> Memory, Skills, AGENTS.md, Tools/MCP, Harness 같은 개입이 AI Agent를 실제로 개선하는지 실험으로 검증합니다.

<div align="center">

![PseudoLab](https://img.shields.io/badge/PseudoLab-S13-3776AB)
![Discord Community](https://img.shields.io/badge/Discord-BF40BF)
![Stars](https://img.shields.io/github/stars/Pseudo-Lab/Agentproof)
![Forks](https://img.shields.io/github/forks/Pseudo-Lab/Agentproof)
![Pull Requests](https://img.shields.io/github/issues-pr/Pseudo-Lab/Agentproof)
![Issues](https://img.shields.io/github/issues/Pseudo-Lab/Agentproof)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

**프로젝트 페이지:** https://pseudo-lab.com/projects/a6584971-2f7c-47a5-b9c4-42ae174bf8db

</div>


## 파일럿 PR 제출 시작하기

[제출 안내](docs/SUBMISSION_GUIDE.md)를 따라 `templates/experiment/`를 복사하고,
카드·코드·설정·파일럿 로그를 함께 제출하세요.

- [복사용 실험 카드](templates/experiment/CARD.md)
- [작성 완료된 오프라인 예시](experiments/E00-offline-example/CARD.md) — 실제 모델 결과가 아닌 mock 연습
- [공통 실험·로그 규칙](docs/EXPERIMENT_PROTOCOL.md)

API 키 없이 예시 로그를 확인하려면 레포 루트에서 실행하세요 (Python 3.10+).

```sh
python3 harness/summarize.py experiments/E00-offline-example/results/pilot/example-001
```

## 러너 모집 안내

| 항목 | 내용 |
| --- | --- |
| 모집 | 2026년 9월 18일 ~ 9월 28일 |
| 선정 발표 | 2026년 10월 1일 |
| 활동 | 2026년 10월 4일 ~ 2027년 1월 9일 (Grand Gathering) |
| 기간 | 시즌 프레임 16주 / 실활동 14주 (활동 12주 + 방학 2주) |
| 정원 | Builder 1 + Runner 최대 8 |
| 모임 | 매주 화요일 21:00–22:00 KST, Discord |
| 부담 | 모임 1시간 + 주간 외부 3–5시간 |

지원: [가짜연구소 프로젝트 페이지](https://pseudo-lab.com/projects/a6584971-2f7c-47a5-b9c4-42ae174bf8db)

## ✨ Why this project?

에이전트에 Memory를 붙이고, Skill을 추가하고, system context를 정리하면 좋아진 것처럼 보일 때가 많습니다. 하지만 새로운 구성 요소를 추가했다는 사실과 실제 성능이 개선됐다는 사실은 다릅니다.

한 번 성공했지만 반복 실행에서는 흔들릴 수도 있고, 성공률은 올랐지만 token과 비용이 크게 증가할 수도 있습니다. 특정 모델이나 task에서만 효과가 있었을 가능성도 있습니다.

AgentProof에서는 이런 질문을 직접 실험합니다.

- Memory를 붙이면 실제 task success가 올라갈까?
- `AGENTS.md`나 `CLAUDE.md`는 어떤 조건에서 도움이 될까?
- Agent Skills는 많을수록 좋을까?
- Tool/MCP 추가로 얻는 성능 향상이 추가 context와 비용을 정당화할까?
- Harness나 routing 전략의 효과는 반복 실행에서도 유지될까?

각 Runner는 하나의 질문을 자신의 연구 질문으로 구체화하고, baseline과 intervention을 직접 설계해 검증합니다.

### 비슷한 S13 프로젝트와의 차이

| 프로젝트 | 한 줄 |
| --- | --- |
| All About Harness | Agent **구조**를 분해·구현 |
| Agent 경험치 연구소 | Memory vs Skill 변경의 **한 가지 RQ**를 깊게 |
| 나만의 AI Agent 만들기 | 개인 Agent **제작·Demo** |
| **AgentProof** | 여러 개입을 **동일 평가 체계**로 비교하고 **교차 재현** |

핵심: “좋아 보인다”가 아니라 **어떤 조건에서 실제로 개선되는지**를 증명합니다. 자세한 포지셔닝은 [`docs/POSITIONING.md`](docs/POSITIONING.md).

## 🎯 Goal

이번 시즌의 목표는 **"좋아 보인다"를 넘어, 어떤 개입이 어떤 조건에서 실제로 도움이 되는지 재현 가능한 실험으로 남기는 것**입니다.

- [ ] **Milestone 1** — 공통 환경에서 baseline–intervention 실험
- [ ] **Milestone 2** — Runner별 Research Proposal 확정
- [ ] **Milestone 3** — 개인 실험 및 reliability 검증
- [ ] **Milestone 4** — 다른 Runner의 실험 cross-reproduction
- [ ] **Milestone 5** — Experiment Board와 OSS v1.0 공개

성공 기준(정량)은 [`docs/SUCCESS_CRITERIA.md`](docs/SUCCESS_CRITERIA.md)를 따릅니다.

## 📦 Expected Outcome

- Runner별 재현 가능한 Agent Evaluation 실험
- 실험 질문·설계·결과를 정리한 Experiment Card ([템플릿](templates/EXPERIMENT_CARD.example.md))
- 결과를 비교하는 Experiment Board
- 공통 evaluation harness
- baseline–intervention 비교, reliability·context·cost 분석, cross-reproduction 결과를 담은 통합 리포트
- 누구나 같은 절차로 다시 실행할 수 있는 오픈소스 v1.0

## 🧪 How We Experiment

모든 실험은 가능한 한 같은 task, model, setting에서 baseline과 intervention을 비교합니다.

성능뿐 아니라 반복 실행에서의 안정성, context/token 사용량, 비용을 함께 기록합니다. 서로 다른 benchmark의 절대 점수를 직접 비교하기보다, 각 환경 안에서 baseline 대비 변화와 반복 실행의 안정성을 중심으로 봅니다.

예상과 다른 결과나 성능 하락도 실패로 버리지 않습니다. 재현할 수 있고 어떤 조건에서 효과가 없었는지 설명할 수 있다면 하나의 결과로 남깁니다.

후반에는 다른 Runner의 실험을 직접 재현합니다. 우선 같은 조건에서 결과가 반복되는지 확인하고, 가능하다면 모델이나 환경을 바꿨을 때도 같은 방향의 결과가 유지되는지 살펴봅니다.

### 대표 연구 질문 예시

1. Memory 추가가 성공률은 높이지만 context cost를 얼마나 늘리는가?
2. MCP tool 추가가 task success와 latency에 미치는 영향은?
3. `SKILL.md`의 절차 명시가 반복 실행 reliability를 개선하는가?
4. Harness retry가 단순 재시도보다 비용 효율적인가?

## ✅ Success Criteria (요약)

| 구분 | 기준 |
| --- | --- |
| 개인 | RQ 1개, Experiment Card ≥1, baseline/intervention **≥5회** 반복, cross-reproduction 1회 |
| 공통 | 공통 task ≥3, harness + Board, 시도별 성공·토큰·비용 로그와 정의된 reliability 요약 |
| 운영 | 매주 GitHub에 코드·설정·결과·의사결정 중 ≥1 기록 |
| v1.0 | 신규 기여자가 README만으로 baseline 1회 재현 가능 |

전체 체크리스트: [`docs/SUCCESS_CRITERIA.md`](docs/SUCCESS_CRITERIA.md)

## 👥 Roles

역할 상세: [`docs/ROLES.md`](docs/ROLES.md)

| Role | Focus |
| --- | --- |
| Experiment Design | RQ · 가설 · metric |
| Agent / Harness Engineering | baseline · intervention 구현 |
| Evaluation & Metrics | success · reliability · cost |
| Data / Log Analysis | 표 · 해석 |
| Reproduction QA | 교차 재현 |
| Documentation & Presentation | Card · Board · 발표 |
| Open-source Release | README · 릴리스 |

## 🗺️ Schedule frame

- **시즌 프레임:** 16주 (사이트 헤더 기준)
- **실활동:** 14주 = 활동 12주 + 연말 방학 2주
- **W16:** 최종 릴리스 후 회고 · 비동기 정리

| Week | Date | Focus |
| --- | --- | --- |
| W01 | 10/07 | **OT & Shared Environment** — 공용 실험 환경 세팅 |
| W02 | 10/14 | **Baseline & Common Intervention** — 공통 task로 실험 사이클 연습 |
| W03 | 10/21 | **Research Question & Experiment Design** |
| W04 | 10/28 | **Research Proposal Day** — 전원 설계 확정 |
| W05 | 11/04 | **Implementation & First Experiment** |
| W06 | 11/11 | **Analysis & Peer Debugging** |
| W07 | 11/18 | **First Results Day A** |
| W08 | 11/25 | **First Results Day B** + Experiment Board 반영 |
| W09 | 12/02 | **Ablation & Efficiency** |
| W10 | 12/09 | **Reliability & Repeated Runs** |
| W11 | 12/16 | **Validation Day A** |
| — | 12/23 | **방학** |
| — | 12/30 | **방학** |
| W12 | 01/06 | **Validation Day B & Cross-Reproduction** |
| 🎉 | 01/09 | **Grand Gathering & OSS v1.0** |
| W16 | 시즌 프레임 | 회고 · 문서 정리 · 비동기 팔로업 |

## 🙋 Who Can Join?

Agent 개발이나 연구 경험은 필수가 아닙니다. Python과 GitHub를 기본적으로 사용할 수 있고, LLM·AI Agent에 관심이 있다면 참여할 수 있습니다.

특히 이런 분과 잘 맞습니다.

- "이걸 붙이면 진짜 좋아질까?"를 직접 확인해보고 싶은 분
- 코드를 만드는 데서 끝내지 않고 결과를 수치와 기록으로 설명하고 싶은 분
- 예상과 다른 결과도 숨기지 않고 함께 파고드는 것을 좋아하는 분
- 하나의 연구 질문을 시즌 동안 끝까지 실험해보고 싶은 분

### 온보딩 (첫 주)

- Discord 참가 + 화요일 21:00–22:00 **KST** 캘린더 등록
- 이 repo fork/clone, Python 3.10+ 확인
- API 키·비용: 개인 키 사용 시 **주간 예산 상한**을 Builder와 합의 (팀 공용 키 정책은 OT에서 안내)
- 권장: `templates/EXPERIMENT_CARD.example.md` 복사해 연습 Card 1장 작성
- 주간 외부 작업 권장: **3–5시간** (모임 1시간 별도)

모든 Runner는 매주 코드, 실험 설정, 결과, 의사결정 중 최소 하나를 GitHub에 기록합니다.

## 📅 Recruitment & Meeting

- **Meeting:** Every Tuesday, 21:00–22:00 KST
- **Format:** Pseudo Lab Discord
- **Team Size:** Builder 1 + Runners up to 8
- **Duration:** 시즌 16주 프레임 / 실활동 14주(12+방학2)

모집·선정 일정은 [프로젝트 페이지](https://pseudo-lab.com/projects/a6584971-2f7c-47a5-b9c4-42ae174bf8db) 공지를 따릅니다.

## 📁 Repo layout

```
docs/           # 제출 안내, 실험 규칙, 성공 기준
templates/experiment/  # 복사용 카드·설정·오프라인 실행 예시
experiments/    # 연구 질문별 실험 패키지 (E00은 mock 예시)
reproductions/  # 다른 참여자의 교차 재현
harness/        # 공통 결과 규격·로그 검증·요약
report/         # 통합 기술보고서 작성 틀
board/          # 검토한 연구 결과 비교표 안내
```

## Acknowledgement 🙏

이 프로젝트는 가짜연구소 Open Academy로 진행됩니다.

AgentProof is developed as part of Pseudo-Lab's Open Research Initiative. Special thanks to all runners, contributors, and the open-source research community.

## About Pseudo Lab 👋🏼

[Pseudo Lab](https://pseudo-lab.com/) is a non-profit community focused on advancing machine learning and AI through open collaboration.

Built around the values of **Sharing, Motivation, and Collaborative Joy**, Pseudo Lab brings together builders, researchers, learners, and contributors to experiment, share knowledge, and create open-source projects together.

## Contributors 😃

<a href="https://github.com/Pseudo-Lab/Agentproof/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Pseudo-Lab/Agentproof" />
</a>

## License 🗞

This project is licensed under the [MIT License](LICENSE).
