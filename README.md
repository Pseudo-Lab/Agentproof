# AgentProof

> Memory, Skills, AGENTS.md, Tools/MCP, Harness 같은 개입이 AI Agent를 실제로 개선하는지 실험으로 검증합니다.

<div align="center">

![PseudoLab](https://img.shields.io/badge/PseudoLab-S13-3776AB)
![Discord Community](https://img.shields.io/badge/Discord-BF40BF)
![Stars](https://img.shields.io/github/stars/Pseudo-Lab/Agentproof)
![Forks](https://img.shields.io/github/forks/Pseudo-Lab/Agentproof)
![Pull Requests](https://img.shields.io/github/issues-pr/Pseudo-Lab/Agentproof)
![Issues](https://img.shields.io/github/issues/Pseudo-Lab/Agentproof)

</div>

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

## 🎯 Goal

이번 시즌의 목표는 **"좋아 보인다"를 넘어, 어떤 개입이 어떤 조건에서 실제로 도움이 되는지 재현 가능한 실험으로 남기는 것**입니다.

- [ ] **Milestone 1** — 공통 환경에서 baseline–intervention 실험
- [ ] **Milestone 2** — Runner별 Research Proposal 확정
- [ ] **Milestone 3** — 개인 실험 및 reliability 검증
- [ ] **Milestone 4** — 다른 Runner의 실험 cross-reproduction
- [ ] **Milestone 5** — Experiment Board와 OSS v1.0 공개

## 📦 Expected Outcome

최종적으로 다음과 같은 결과물을 만드는 것을 목표로 합니다.

- Runner별 재현 가능한 Agent Evaluation 실험
- 실험 질문·설계·결과를 정리한 Experiment Card
- 결과를 비교하는 Experiment Board
- 공통 evaluation harness
- baseline–intervention 비교, reliability·context·cost 분석, cross-reproduction 결과를 담은 통합 리포트
- 누구나 같은 절차로 다시 실행할 수 있는 오픈소스 v1.0

## 🧪 How We Experiment

모든 실험은 가능한 한 같은 task, model, setting에서 baseline과 intervention을 비교합니다.

성능뿐 아니라 반복 실행에서의 안정성, context/token 사용량, 비용을 함께 기록합니다. 서로 다른 benchmark의 절대 점수를 직접 비교하기보다, 각 환경 안에서 baseline 대비 변화와 반복 실행의 안정성을 중심으로 봅니다.

예상과 다른 결과나 성능 하락도 실패로 버리지 않습니다. 재현할 수 있고 어떤 조건에서 효과가 없었는지 설명할 수 있다면 하나의 결과로 남깁니다.

후반에는 다른 Runner의 실험을 직접 재현합니다. 우선 같은 조건에서 결과가 반복되는지 확인하고, 가능하다면 모델이나 환경을 바꿨을 때도 같은 방향의 결과가 유지되는지 살펴봅니다.

## 🗺️ 14-Week Roadmap (12주 활동 + 방학 2주)

| Week | Date | Focus |
| --- | --- | --- |
| W01 | 10/07 | **OT & Shared Environment** — 프로젝트 목표와 운영 방식을 공유하고 공용 실험 환경을 세팅합니다. |
| W02 | 10/14 | **Baseline & Common Intervention** — 공통 task에서 baseline과 동일 intervention을 실행하며 실험 사이클을 한 번 연습합니다. |
| W03 | 10/21 | **Research Question & Experiment Design** — 각자의 연구 질문과 실험 설계 초안을 공유합니다. |
| W04 | 10/28 | **Research Proposal Day** — 8명 전원이 질문, 가설, baseline, intervention, 평가 방법을 발표하고 설계를 확정합니다. |
| W05 | 11/04 | **Implementation & First Experiment** — intervention을 구현하고 첫 개인 실험을 실행합니다. |
| W06 | 11/11 | **Analysis & Peer Debugging** — 첫 결과를 분석하고 평가 방식과 blocker를 함께 점검합니다. |
| W07 | 11/18 | **First Results Day A** — A그룹 4명이 첫 결과를 발표합니다. |
| W08 | 11/25 | **First Results Day B** — B그룹 4명이 첫 결과를 발표하고 전체 결과를 Experiment Board에 반영합니다. |
| W09 | 12/02 | **Ablation & Efficiency** — 성능 향상에 기여한 요소와 context/token/cost trade-off를 분석합니다. |
| W10 | 12/09 | **Reliability & Repeated Runs** — 동일 조건을 반복 실행해 단발성 성공과 반복 신뢰성을 구분합니다. |
| W11 | 12/16 | **Validation Day A** — A그룹 4명이 추가 실험과 검증 결과를 발표합니다. |
| — | 12/23 | **방학** |
| — | 12/30 | **방학** |
| W12 | 01/06 | **Validation Day B & Cross-Reproduction** — B그룹 검증 결과 발표 후 다른 Runner의 실험을 같은 조건으로 재현합니다. |
| 🎉 | 01/09 | **Grand Gathering & OSS v1.0** — 각자의 연구 과정을 발표하고 프로젝트 전체 결과와 오픈소스 v1.0을 공개합니다. |

## 👥 Team

| Role | Name | Focus |
| --- | --- | --- |
| 🧭 Builder | Hyeonseo Jang | Project direction & experiment framework |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |
| 🏃 Runner | Recruiting | |

## 🙋 Who Can Join?

Agent 개발이나 연구 경험은 필수가 아닙니다. Python과 GitHub를 기본적으로 사용할 수 있고, LLM·AI Agent에 관심이 있다면 참여할 수 있습니다.

특히 이런 분과 잘 맞습니다.

- "이걸 붙이면 진짜 좋아질까?"를 직접 확인해보고 싶은 분
- 코드를 만드는 데서 끝내지 않고 결과를 수치와 기록으로 설명하고 싶은 분
- 예상과 다른 결과도 숨기지 않고 함께 파고드는 것을 좋아하는 분
- 하나의 연구 질문을 16주 동안 끝까지 실험해보고 싶은 분

모든 Runner는 매주 코드, 실험 설정, 결과, 의사결정 중 최소 하나를 GitHub에 기록합니다.

## 📅 Schedule

- **모집 시작**: 2025년 9월 18일
- **모집 마감**: 2025년 9월 28일
- **선정 발표**: 2025년 10월 1일
- **활동 시작**: 2025년 10월 4일
- **활동 종료**: 2026년 1월 9일 (Grand Gathering)
- **Duration**: 12주 활동 + 방학 2주
- **Meeting**: Every Tuesday, 21:00–22:00 KST
- **Format**: Pseudo Lab Discord
- **Team Size**: Builder 1 + Runners up to 8

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

This project is licensed under the MIT License.
