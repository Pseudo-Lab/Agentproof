# E05 — LLM은 검색된 과거 실패 경험을 언제 수용하고 언제 거부해야 하는지 스스로 판단할 수 있는가?

> 상태: 파일럿(탐색적 실험 1~4차) 완료 · 통제 교체(Paired Memory Swap) 본실험 설계 확정  
> 실험 ID: E05 (`E05-memory-applicability`)  
> 담당자: 김형섭 (`hyungsseop`)  
> 실행 모드: real (`google/gemma-4-31b-it` via OpenRouter, `temperature=0.0`, `seed=42`, 단일 프롬프트 평가)

## 1. 연구 배경 및 목적

LLM 에이전트는 과거 실패 경험을 Memory로 저장하고 유사한 작업에 재사용할 수 있다. 하지만 작업의 표면적 유사성은 실패 원인이나 과거 경험의 적용 가능성을 보장하지 않는다. 검색된 Memory가 현재 Trajectory에 부적절하면 오히려 실패 원인 진단을 악화시킬 수 있다.

기존 연구와 실험 관찰에 따르면, **LLM은 과거 Memory의 적용을 보수적으로 제한하면 유용한 경험까지 거부하고, 적극적으로 활용하도록 유도하면 부적절한 경험까지 수용하는 경향**을 보인다. 본 연구는 Retrieval 알고리즘의 개선보다 **LLM이 현재 Trajectory의 근거에 기반하여 Memory의 적용 가능성을 정확히 판단하고, 그 판단을 최종 실패 진단에 일관되게 반영할 수 있는가**를 탐구한다.

- **RQ1 — Memory Applicability Judgment:** LLM은 현재 Trajectory를 바탕으로 적절한 Memory는 수용하고 부적절한 Memory는 거부할 수 있는가?
- **RQ2 — Evidence-to-Decision Consistency:** 모델이 현재 Trajectory에서 찾아낸 지지·반박 근거가 Memory 적용 판단과 최종 실패 진단에 일관되게 반영되는가?

---

## 2. 실험 환경

| 항목 | 설정 |
|---|---|
| 작업 | BenchTrace (`ALFWorld`) 실패 Trajectory의 진단 대상 구간(`[Step s ~ Step e]`) 실패 원인 분류 |
| 분류 체계 (Taxonomy) | 7개 실패 라벨 (`strategy/goal_misinterpretation`, `strategy/missing_processing_step`, `strategy/missing_destination`, `strategy/exhaustive_rescan`, `strategy/loop`, `operation/wrong_object_pick`, `operation/move_command_avoidance`) |
| Memory 구성 | 과거 실패 에피소드(Memory Bank `N=147`)에서 검색된 실패 사례 요약 |
| Retrieval | TF-IDF 고정 (`top_k=1`, 동일 Goal 검색 제외 `exclude_same_goal=True`, `lesson_mode="template"`, `memory_show_type=False`) |
| 데이터 분할 | Goal 단위 분할 ([`data/split.json`](data/split.json), `seed=42`): Memory Bank `N=147`, Pilot `N=30`, Test `N=100`, 추가 평가 `N=159` |
| 평가 모델 | `google/gemma-4-31b-it` (OpenRouter API, `temperature=0.0`, `max_tokens=2048`) |

- **데이터 독립성 주의사항:** 추가 평가 집합(`N=159`)은 3.3절 실험(보수적인 비교 적용성 검토) 당시에는 미사용 평가 집합이었으나, 그 결과를 오류 분석한 뒤 설계한 3.4절 실험(구간 구조를 강화한 비교 판단)에 대해서는 독립적인 Holdout이 아니다.

---

## 3. 실험 진행 과정

### 3.1 LLM은 검색된 과거 경험을 스스로 판단할 수 있을까?

본 연구는 검색된 과거 실패 경험이 현재 상황에 적절한지 LLM이 스스로 구별할 수 있는지 확인하는 것에서 시작하였다. 이를 위해 Memory를 사용하지 않는 경우, 검색된 Memory를 그대로 제공하는 경우, 모델이 Memory의 적용 여부를 직접 판단하는 경우를 비교하였다.

예를 들어 현재 에이전트가 물체를 목적지까지 이동시켰지만 필요한 처리 행동을 수행하지 못한 상황이라고 가정하자. 이때 과거 Memory가 *"목적지에 도착하지 못해 실패했다"*는 경험을 설명한다면, 두 작업은 유사하더라도 실패 원인은 다르다. 따라서 적절한 판단은 과거 Memory를 그대로 적용하지 않고 현재 Trajectory를 기준으로 실패 원인을 진단하는 것이다.

그러나 초기 실험에서는 단순히 Memory를 제공하거나 모델에게 적용 여부를 직접 판단하도록 하는 것만으로는 진단 성능이 개선되지 않았다 ([`results/pilot/pilot-initial-n100/`](results/pilot/pilot-initial-n100/)).

| 방법 | 설명 | 정확도 (`Test N=100`) | 해로운 교정 (정답→오답) | 유익한 교정 (오답→정답) |
|---|---|---:|---:|---:|
| Memory 없이 진단 | 현재 Trajectory만 보고 실패 원인을 판단 | 54.0% | — | — |
| Memory 직접 제공 | 검색된 과거 경험을 함께 제공 (`baseline`) | 53.0% | 6건 | 5건 |
| 모델의 자율적 적용 판단 | LLM이 과거 경험을 적용할지(`yes/no`) 직접 결정 (`intervention`) | 50.0% | 10건 | 6건 |
| 근거 기반 적용 제한 | 현재 근거를 확인하고 외부 규칙으로 부적절한 적용 제한 | 56.0% | 1건 | 3건 |

특히 모델이 적용 여부를 직접 판단하도록 했음에도 정확도가 가장 낮았고(50.0%), 기존 정답이 오답으로 바뀌는 해로운 교정이 10건 발생하였다. 반면 외부에서 반박 근거 유무에 따른 적용 제한 규칙을 강제한 경우에만 해로운 교정이 1건으로 줄었다. 이를 통해 **LLM에게 Memory의 적용 가능성을 판단하라고 지시하는 것만으로는 부적절한 과거 경험을 스스로 걸러내지 못한다**는 문제를 확인하였다.

---

### 3.2 Memory를 지지하거나 반박하는 근거를 찾도록 하면 달라질까?

초기 실험을 분석하는 과정에서 모델이 현재 Trajectory에서 Memory와 모순되는 근거를 발견하고도, 최종적으로 해당 Memory를 적용하는 사례가 나타났다. 이에 따라 외부 제한 규칙을 제거하고, 모델이 Memory를 적용하기 전에 현재 실행 기록에서 이를 지지하거나 반박하는 근거를 명시적으로 찾도록 하였다 ([`results/pilot/pilot-factorial-n100/`](results/pilot/pilot-factorial-n100/)).

> **실제 로그 사례 (`alfworld_pick_two_evomemory_01_gpt-4.1_inst001@5-50`, `Test N=100`)**
> - **현재 상황 및 실제 실패 원인:** 리모컨 2개를 찾아 안락의자(`armchair`)에 놓는 과제. 에이전트는 이미 안락의자 위치를 알고 첫 번째 리모컨을 놓은 뒤, 두 번째 리모컨을 찾으며 같은 서랍과 선반만 반복 확인함 (정답 및 초기 진단: `반복 행동 / strategy/loop`).
> - **검색된 과거 Memory:** *"목적지(안락의자)를 한 번도 확인하지 않아 도착하지 못해 실패했다 (`strategy/missing_destination`)."*
> - **모델의 실제 출력:**
>   - **지지 근거 (4개):** Step 22~49에서 두 번째 리모컨을 안락의자에 놓지 못함.
>   - **반박 근거 (1개):** *"Step 13에서 이미 `go to armchair 1` 및 `put remotecontrol 1 in/on armchair 1`을 수행하여 목적지 위치를 알고 방문했음."*
> - **문제 현상:** 모델이 Step 13이라는 명확한 반박 근거를 직접 작성하고도, 후반부에 안락의자에 가지 못했다는 사실에 끌려 최종 결정을 `apply`로 내리고 진단을 `목적지 미방문(missing_destination)`으로 잘못 변경하였다(정답 → 오답).

단순히 지지 근거와 반박 근거를 작성하도록 하는 것만으로는 문제가 해결되지 않았기 때문에, 다음 두 가지 구조적 변경도 2×2 요인으로 함께 비교하였다 (`Test N=100`).

1. **Memory의 입력 위치 변경 (Trajectory-First vs Memory-First):** 기존에는 현재 Trajectory를 먼저 제공하고 과거 Memory를 나중에 제공했다. 이를 반대로 배치하여 과거 경험이 초기 진단에 미치는 영향을 확인하였다. 하지만 Memory를 먼저 제공한 경우에도 부적절한 경험의 영향이 줄어들지 않았고, 진단 정확도가 오히려 하락하였다(`48.0% → 44.0%`).
2. **근거 검토 방식의 구조화 (단순 배열 vs 구조화 감사):** 단순히 지지·반박 근거를 배열로 출력하는 대신, 근거의 존재 여부(`found / not_found`), 관련 Step 번호, 판단 이유를 각각 명시하도록 하였다. 그러나 근거를 더 구조적으로 출력하더라도 잘못된 Memory 적용이 충분히 감소하지 않았다(`48.0% → 47.0%`).

| 입력 순서 및 근거 출력 방식 | 정확도 (`Test N=100`) | 유익한 교정 (오답→정답) | 해로운 교정 (정답→오답) |
|---|---:|---:|---:|
| Trajectory 먼저 + 단순 근거 배열 | 48.0% | 2건 | 8건 |
| Memory 먼저 + 단순 근거 배열 | 44.0% | 3건 | 10건 |
| Trajectory 먼저 + 구조화된 양면 근거 검토 | 47.0% | 5건 | 11건 |
| Memory 먼저 + 구조화된 양면 근거 검토 | 43.0% | 3건 | 14건 |

이 과정에서 중요한 문제를 발견하였다. **과거 Memory가 현재 Trajectory의 일부 사실과 일치한다고 해서(Factual Consistency), 그 Memory가 현재 실패 원인을 가장 정확하게 설명하는 것은 아니다(Diagnostic Applicability).** 예를 들어 에이전트가 같은 장소를 반복 방문하면서 결과적으로 목적지에 도착하지 못했다면, '반복 행동'과 '목적지 미도달'이라는 두 설명 모두 현재 실행 기록의 사실과 일치할 수 있다. 따라서 단순히 Memory와 일치하는 근거가 존재하는지만 확인하는 것은 충분하지 않았다.

---

### 3.3 과거 Memory와 현재 진단 중 어느 쪽이 더 적절한지 비교하도록 하면 어떨까?

앞선 문제를 해결하기 위해 Memory를 지지하거나 반박하는 근거의 존재 여부만 확인하는 방식에서 벗어나, **현재 Trajectory만으로 내린 초기 진단과 과거 Memory가 제시하는 진단을 직접 비교**하도록 하였다 ([`results/pilot/pilot-comparative-n159/`](results/pilot/pilot-comparative-n159/)). 이때 다음 세 가지를 검토하게 하였다.

- **진단 대상 구간의 일치 여부 (Scope Match):** 과거 Memory가 전체 에피소드가 아니라 현재 분석해야 하는 구간(`[Step s ~ Step e]`)의 실패를 설명하는가?
- **두 진단을 구별하는 근거 (Discriminative Support):** 두 진단에 모두 부합하는 공통 사실이 아니라, 과거 Memory가 초기 진단보다 적절하다고 판단할 만한 구별적 근거가 있는가?
- **핵심 실패에 대한 설명력 (Explanatory Relevance):** 과거 Memory가 현재 실패의 핵심 원인을 설명하는가, 아니면 함께 나타난 부차적 현상을 설명하는가?

이 방식에서는 잘못된 Memory를 적용하여 기존 정답을 오답으로 변경하는 사례가 크게 감소하였다. 추가 평가 집합 159개 사례에서, 기본적인 구조화 근거 검토 방식은 기존 정답을 오답으로 변경한 사례가 23건이었지만, 두 진단의 상대적 적합성을 비교하도록 한 방식에서는 1건으로 감소하였다.

| 방법 (`추가 평가 N=159`) | 정확도 | 유익한 교정 (오답 → 정답) | 해로운 교정 (정답 → 오답) |
|---|---:|---:|---:|
| Memory 없이 진단 | 51.6% (82/159) | — | — |
| 단순 근거 배열 검토 | 40.9% (65/159) | 9건 | 22건 |
| 구조화된 양면 근거 검토 (`baseline`) | 40.3% (64/159) | 8건 | 23건 |
| 보수적인 비교 적용성 검토 (`intervention`) | 50.3% (80/159) | 2건 | 1건 |

그러나 예상하지 못한 문제가 발생하였다. **잘못된 Memory를 거부하는 데는 효과적이었지만, 실제로 도움이 되는 Memory까지 거부하는 경우가 많아진 것이다** (`유익한 교정 8~9건 → 2건`).

> **실제 로그 사례 (`alfworld_look_at_obj_evomemory_00_gpt-4.1_inst004@6-50`, `추가 평가 N=159`)**
> - **현재 상황 및 실제 실패 원인:** 책상 스탠드(`desklamp`) 불빛 아래에서 펜(`pen`)을 살펴보는 과제(`Step 6~50`). 에이전트가 Step 6에서 펜을 집은 뒤 스탠드를 확인하지 않고 엉뚱한 서랍장·선반만 반복 탐색함 (정답: `반복 행동 / strategy/loop`).
> - **초기 진단 vs 과거 Memory:** 초기 진단은 `목표 오해(strategy/goal_misinterpretation)`로 오답이었고, 검색된 과거 Memory는 *"물체를 집은 뒤 같은 장소들을 반복 재방문하며 루프에 빠졌다(`strategy/loop`)"*로 정답을 제시하고 있었다.
> - **모델의 실제 판단:** 모델은 현재 기록(Step 11, 20, 29, 41)에서 반복 방문 근거를 찾았음에도, *"반복 방문은 목표 오해로 인해 나타난 부차적 증상일 뿐이므로 초기 진단(`목표 오해`)이 더 근본적인 설명이다"*라고 보수적으로 해석하여 유용한 Memory를 **거부(`keep_initial`)**하고 오답을 유지하였다.

즉, Memory의 적용 기준을 엄격하게 만들자 잘못된 Memory 적용으로 인한 진단 악화는 크게 줄었지만, 유익한 경험의 활용도 함께 억제되었다.

---

### 3.4 유용한 Memory를 더 적극적으로 활용하도록 하면 어떨까?

앞선 방식에서는 잘못된 Memory 적용을 크게 줄였지만, 유용한 Memory를 통한 정답 교정도 감소하였다. 이를 개선하기 위해 특정 라벨에 대한 예외 규칙 없이 현재 Trajectory의 구간 구조를 더 자세히 검토하도록 하였다 ([`results/pilot/pilot-span-tradeoff-n159/`](results/pilot/pilot-span-tradeoff-n159/)). 구체적으로는 다음을 확인하도록 했다.

- 현재 분석 구간이 어떤 행동이나 상태 변화에서 시작되는가?
- 이후 어떤 행동이나 실패가 반복되거나 지속되는가?
- 관찰된 행동이 실패의 원인인가, 결과인가, 아니면 함께 나타나는 현상인가?
- 과거 Memory와 현재 초기 진단 중 어느 쪽이 현재 구간 전체를 더 잘 설명하는가?

그 결과, 과거 Memory를 활용해 잘못된 초기 진단을 정답으로 수정하는 사례가 증가하였다(`2건 → 8건`). 그러나 동시에 부적절한 Memory를 적용하여 정답을 오답으로 변경하는 사례도 함께 증가하였다(`1건 → 10건`).

| 방법 (`추가 평가 N=159`) | 정확도 | 유익한 교정 (오답 → 정답) | 해로운 교정 (정답 → 오답) |
|---|---:|---:|---:|
| 보수적인 비교 적용성 검토 (`baseline`) | 50.3% (80/159) | 2건 | 1건 |
| 구간 구조를 강화한 비교 판단 (`intervention`) | 49.7% (79/159) | 8건 | 10건 |
| *(보조 비교)* 구간 시작점 확인 + 탐색 라벨 간 적용 제한 | 54.1% (86/159) | 4건 | 2건 |

> **실제 로그 사례 (구간 구조 강화 시 나타난 양면성, `추가 평가 N=159`)**
> - **유익한 교정 성공 (`alfworld_look_at_obj_evomemory_02_Qwen_Qwen3-32B_inst004@2-50`):** 구간 시작점(Step 2~5에서 펜과 스탠드를 이미 발견한 뒤 Step 6부터 스탠드를 켜지 않은 채 다른 곳만 탐색)을 검토하게 하자, 초기 진단의 `목표 오해` 대신 과거 Memory가 제시한 `필수 처리 단계 누락(strategy/missing_processing_step)`을 수용하여 정답으로 교정하였다.
> - **해로운 교정 발생 (`alfworld_pick_heat_evomemory_00_gpt-4.1_inst003@5-50` 외 6건):** 에이전트가 달걀을 데운 뒤 식탁에 놓지 않고 이미 확인한 장소들을 다시 도는 구간에서 초기 진단이 `반복 행동(strategy/loop)`으로 맞았음에도, 구간 전체의 이동 궤적을 넓게 해석하라는 지시 때문에 과거 Memory가 제시한 `전수 재탐색(strategy/exhaustive_rescan)` 설명도 구간 전개와 부합한다고 받아들여 정답을 오답으로 변경하였다.

한편, 구간 시작점(`[Step s]`) 전이 확인에 더해 특정 탐색 라벨(`loop` ↔ `exhaustive_rescan`) 간의 교차 덮어쓰기를 제한한 보조 비교 조건에서는 정확도가 `54.1%`를 기록하였다. 그러나 이는 특정 분류 체계의 라벨 간 제한 규칙이 개입된 결과이므로, LLM의 자율적이고 범용적인 Memory Applicability 판단 능력이 해결된 증거로 해석하지 않는다.

---

### 3.5 실험을 통해 발견한 핵심 문제

본 연구는 검색된 과거 경험이 현재 상황에 적절한지 LLM이 스스로 판단할 수 있는지 확인하기 위해 시작되었다.

1. 초기 실험에서는 LLM에게 Memory 적용 여부를 직접 판단하도록 해도 부적절한 경험을 충분히 걸러내지 못했다.
2. 이후 현재 Trajectory에서 Memory를 지지하거나 반박하는 근거를 검토하도록 하였지만, **일부 사실과 일치하는 근거를 발견하는 것(Factual Consistency)**과 **현재 실패 원인을 더 잘 설명하는지 판단하여 결정에 반영하는 것(Diagnostic Applicability & Consistency)**은 별개의 문제임을 확인하였다.
3. 이를 개선하기 위해 Memory와 초기 진단의 상대적인 적합성을 보수적으로 비교하도록 하자 잘못된 Memory 적용이 크게 감소하였으나(`23건 → 1건`), 실제로 유용한 Memory까지 과도하게 거부하는 문제가 발생하였다(`유익한 교정 2건`).
4. 반대로 구간의 전개 과정과 인과적 관계를 더 자세히 검토하여 유용한 Memory의 활용을 확대하자, 유익한 교정(`2건 → 8건`)과 해로운 교정(`1건 → 10건`)이 함께 증가하였다.

**즉, 과거 Memory의 적용을 보수적으로 제한하면 유용한 경험까지 거부하고, 적극적으로 활용하도록 유도하면 부적절한 경험까지 수용하는 상충 관계(Acceptance–Rejection Trade-off)가 관찰되었다.**

---

## 4. 한계 및 해석 시 유의사항

- **독립적인 적합성 정답(Applicability Ground Truth)의 부재:** 현재 분석에서는 과거 Memory의 실패 라벨과 현재 구간의 정답 라벨이 일치하는지(`Label Alignment`)를 대리지표로 활용했다. 그러나 라벨이 같아도 세부 맥락이 다를 수 있으므로, 실제 적용 가능성에 대한 별도의 검증 기준이 필요하다.
- **모델이 출력한 근거 상태와 실제 타당성의 구별:** 모델이 반박 근거를 `not_found`로 출력하거나 지지 근거를 빈 배열(`[]`)로 출력했다고 해서 실제로 근거 탐색만 실패하고 판단 일관성 오류는 0%라고 단정할 수 없다. 모델이 궤적의 근거를 잘못 해석했는지, 근거는 찾았으나 우선순위를 잘못 매겼는지는 별도로 검증해야 한다.
- **추가 평가 집합(`N=159`)의 사후 분석 사용:** 3.4절의 구간 구조 강화 실험은 `N=159`에서 발생한 과잉 거부 사례를 분석한 뒤 설계되었으므로, 동일 집합에서의 수치를 독립적인 일반화 검증으로 간주하지 않는다.
- **후속 통제 실험 미실행:** 아래 5절에 제시된 Paired Memory Swap 및 단계별 오류 분리 실험은 API 사용 한도 도달로 인해 아직 실행하지 않은 후속 계획(사전 등록 설계)이다.

---

## 5. 향후 실험 계획 (미실행 · 본실험 사전 등록 설계)

앞선 실험에서 드러난 과잉 수용과 과잉 거부의 상충 관계를 해결하기 위해, 향후 본실험에서는 단순히 Memory의 수용률을 조절하기보다 **LLM이 현재 Trajectory의 결정적 근거를 통해 적절한 Memory와 부적절한 Memory를 구별하고 이를 최종 진단에 일관되게 반영할 수 있는지**를 다음 세 가지 통제 실험으로 분리하여 검증할 계획이다.

1. **실험 A — Paired Memory Swap (적합성 구별 능력의 직접 검증):**
   - 동일한 Trajectory에 현재 구간과 실제로 부합하는 **적절한 Memory(`M+`)**와 표면적으로만 유사한 **부적절한 Memory(`M−`)**를 각각 쌍(Pair)으로 제공한다.
   - 검색기(Retriever)가 가져온 단일 Memory의 우연한 품질 차이를 통제하고, 모델이 동일한 궤적에서 `M+`는 수용하고 `M−`는 거부하는지(`Applicability Precision / Recall`, `False Acceptance Rate`, `False Rejection Rate`)를 최종 진단 정확도와 분리하여 측정한다.
2. **실험 B — 대칭적·구별적 근거 비교 (Discriminative Evidence Comparison):**
   - 모델이 과거 Memory의 실패 유형을 텍스트에서 추론하는 단계의 오류를 분리하기 위해 실패 유형 명시 여부(`showType`)를 통제한다.
   - 또한 Memory에 대한 근거만 일방적으로 찾는 대신, **초기 진단을 지지하는 근거(`supports_initial`)**, **과거 Memory를 지지하는 근거(`supports_memory`)**, **두 가설 모두와 일치하는 비구별적 사실(`supports_both`)**, 그리고 **두 가설을 가르는 결정적 차이(`decisive_difference`)**를 대칭적으로 비교하도록 한다.
3. **실험 C — 근거-결정 일관성 검증 (Evidence-to-Decision Consistency):**
   - 모델이 인용한 Step 번호와 근거 설명의 사실적 타당성, 해당 근거에 부여한 진단적 의미, 최종 `apply / reject` 결정, 그리고 최종 실패 라벨 선택 사이의 일관성을 단계별로 평가하여 근거 탐색 오류와 의사결정 반영 오류를 분리한다.

---

## 6. 실험 조건과 코드·결과 파일 매핑

본문에서 서술형으로 설명한 각 실험 방법은 이 폴더의 AgentProof 표준 실행 로그 및 원자료 파일에서 다음 식별자와 대응된다.

| 본문 내 실험 명칭 | AgentProof 표준 로그 (`results/pilot/`) | 원자료 JSON/CSV (`results/raw/`) 및 내부 식별자 |
|---|---|---|
| 3.1절 초기 실험 (`Test N=100`) | [`results/pilot/pilot-initial-n100/`](results/pilot/pilot-initial-n100/) (`baseline`=직접 제공 `B`, `intervention`=자율 판단 `C`) | [`initial_test_n100_summary.csv`](results/raw/initial_test_n100_summary.csv), [`test_n100_run1_vs_run2_comparison.csv`](results/raw/test_n100_run1_vs_run2_comparison.csv) (`A`, `B`, `C`, `D`) |
| 3.2절 입력 위치 × 근거 출력 구조 (`Test N=100`) | [`results/pilot/pilot-factorial-n100/`](results/pilot/pilot-factorial-n100/) (`baseline`=단순 배열 `D0`, `intervention`=구조화 검토 `D2`) | [`factorial_d0_d3_ablation.json`](results/raw/factorial_d0_d3_ablation.json) (`D0`, `D1`, `D2`, `D3`) |
| 3.3절 보수적인 비교 적용성 검토 (`N=159`) | [`results/pilot/pilot-comparative-n159/`](results/pilot/pilot-comparative-n159/) (`baseline`=구조화 검토 `D2`, `intervention`=보수적 비교 `D5`) | [`holdout_n159_d0_d2_d4_d5.json`](results/raw/holdout_n159_d0_d2_d4_d5.json), [`d5_missed_beneficial_diagnosis.json`](results/raw/d5_missed_beneficial_diagnosis.json) (`D0`, `D2`, `D4`, `D5`) |
| 3.4절 구간 구조를 강화한 비교 판단 (`N=159`) | [`results/pilot/pilot-span-tradeoff-n159/`](results/pilot/pilot-span-tradeoff-n159/) (`baseline`=보수적 비교 `D5`, `intervention`=구간 구조 강화 `D6-G`) | [`d6_g_t_onset_ablation.json`](results/raw/d6_g_t_onset_ablation.json) (`D5`, `D6_G`, `D6_T`, `Onset`) |

---

## 7. 교차 재현

미실시. API 호출 없이 저장된 로그 검증 및 전체 표/지표 재계산 절차는 [`README.md`](README.md)에 수록하였다.
