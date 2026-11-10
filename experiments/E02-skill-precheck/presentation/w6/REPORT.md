# W6 추가 실험 결과 · 2026-11-09

기존 파일럿을 재현하는 추가 실행이다. 최종 설계의 700회 본실험은 수행하지 않았다. 기존 실행과 새 실행은 합치지 않는다. 모든 실행 trial을 분모에 넣고 API·인프라 오류도 비성공으로 센다. 과거 CARD.md의 SkillsBench 수치는 API 오류를 제외하므로 아래 표와 분모가 다를 수 있다.

새 실행 비용 합계 **$3.850916**. 사용자 허용 $10, 계획 합계 상한 $9. Responses usage에 입력 $0.75/M·출력 $4.50/M을 곱한 캐시 할인 전 리스트 가격 추정치다. 청구서 금액이 아니다.

## 실행 완결성

| 실행 | 수행/계획 | 성공 | 오류 | 비용($) |
|---|---:|---:|---:|---:|
| v3_original | 240/240 | 182/240 | 0 | 2.191515 |
| v4_original | 216/216 | 132/216 | 5 | 10.742001 |
| v3_replication | 180/180 | 141/180 | 0 | 1.798261 |
| v4_replication | 33/72 | 23/33 | 0 | 2.052655 |

## 통제 과제 · E1/L3

스킬이 맞지 않고 근거 파일을 지시하지 않은 칸. 새 입력 seed=20261109, 순서 seed=1109, 같은 모델·문구·도구·채점기·한도. 조건별 칸당 5회. v3의 C2는 소비자 코드·설정·출처 메타데이터라는 위치 유형을 알려주는 문구이며 최종 설계 문구와 다르다.

| 실행 | 과제 | B | C | C2 |
|---|---|---:|---:|---:|
| v3_original | graph | 0/5 | 0/5 | 5/5 |
| v3_original | csv | 0/5 | 0/5 | 4/5 |
| v3_original | events | 0/5 | 0/5 | 0/5 |

**v3_original C2−B**: 과제 평균 +60.00%p, 과제 재표집 95% 구간 [0.0, 100.0].

| v3_replication | graph | 0/5 | 0/5 | 5/5 |
| v3_replication | csv | 0/5 | 0/5 | 4/5 |
| v3_replication | events | 0/5 | 0/5 | 0/5 |

**v3_replication C2−B**: 과제 평균 +60.00%p, 과제 재표집 95% 구간 [0.0, 100.0].

과제 단위 구간은 10,000회 부트스트랩(seed=20261109)이다. 과제가 3개뿐이므로 모집단 일반화나 최종 H1의 확증으로 해석하지 않는다. 기존 카드의 trial 독립 Newcombe 구간과 계산 단위가 다르다.

## SkillsBench · E1

기존 여섯 과제를 모두 유지했다. 과제 입력은 기존 실행과 같고, 새 모델 요청으로 재실행했다. 새 실행은 칸당 2회다. P는 C2에 완료 전 검증을 추가한다. N·V·Hidden 가시성 조작은 아직 적용하지 않았다.

| 실행 | 과제 | B | C2 | P |
|---|---|---:|---:|---:|
| v4_original | threejs-to-obj | 2/3 | 3/3 | 3/3 |
| v4_original | econ-detrending-correlation | 2/3 | 3/3 | 3/3 |
| v4_original | crystallographic-wyckoff-position-analysis | 3/3 | 3/3 | 2/3 |
| v4_original | dapt-intrusion-detection | 2/3 | 1/3 | 2/3 |
| v4_original | r2r-mpc-control | 2/3 | 1/3 | 3/3 |
| v4_original | llm-prefix-cache-replay | 2/3 | 1/3 | 3/3 |

**v4_original C2-B**: 과제 평균 -5.56%p, 과제 재표집 95% 구간 [-27.78, 16.67].

**v4_original P-C2**: 과제 평균 +22.22%p, 과제 재표집 95% 구간 [-5.56, 50.0].
| v4_replication | threejs-to-obj | 1/1 | 0/1 | 1/1 |
| v4_replication | econ-detrending-correlation | 1/1 | 0/1 | 1/1 |
| v4_replication | crystallographic-wyckoff-position-analysis | 1/1 | 1/1 | 1/1 |
| v4_replication | dapt-intrusion-detection | 1/1 | 1/1 | 0/1 |
| v4_replication | r2r-mpc-control | 0/1 | 0/1 | 0/1 |
| v4_replication | llm-prefix-cache-replay | 1/1 | 1/1 | 1/1 |

**v4_replication C2-B**: 과제 평균 -33.33%p, 과제 재표집 95% 구간 [-66.67, 0.0].

**v4_replication P-C2**: 과제 평균 +16.67%p, 과제 재표집 95% 구간 [-33.33, 66.67].

이 비교는 탐색적이다. 과거 P 신호를 본 뒤 골랐고, 단독 검증 V와 위약 N이 없다. 특히 이 원본 과제군에서는 E1이 B 성능을 낮추는지(M1)부터 확인해야 한다. 정답 값이 지시문에 있는 과제 4개와 원래 근거가 다른 파일에 있는 과제 2개는 구분해야 한다.

## 정상 환경과 비용

| 실행 | 조건 | E0 성공 | 전체 회당 비용($) |
|---|---|---:|---:|
| v3_original | A | 22/30 | 0.006998 |
| v3_original | B | 30/30 | 0.008652 |
| v3_original | C | 27/30 | 0.009053 |
| v3_original | C2 | 30/30 | 0.011822 |
| v4_original | A | 3/18 | 0.034770 |
| v4_original | B | 11/18 | 0.046462 |
| v4_original | C | 13/18 | 0.047774 |
| v4_original | C2 | 11/18 | 0.052423 |
| v4_original | P | 13/18 | 0.060744 |
| v4_original | S | 13/18 | 0.056217 |
| v3_replication | B | 30/30 | 0.008383 |
| v3_replication | C | 29/30 | 0.009537 |
| v3_replication | C2 | 30/30 | 0.012051 |
| v4_replication | B | 3/5 | 0.052633 |
| v4_replication | C2 | 5/5 | 0.061479 |
| v4_replication | P | 3/5 | 0.072493 |

## 근거 열람 대리 지표

evidence_opened는 도구 인자에 경로나 파일명이 등장했는지로 계산한 기존 지표다. 실제 열람 성공·이해·적용의 증거로 간주하지 않는다. 실패 사례는 반환 내용과 작성 코드를 직접 확인했다.

| 실행 | 조건 | 근거 경로 등장 | 그중 성공 |
|---|---|---:|---:|
| v3_original | A | 0/15 | 0/0 |
| v3_original | B | 0/15 | 0/0 |
| v3_original | C | 0/15 | 0/0 |
| v3_original | C2 | 11/15 | 9/11 |
| v4_original | A | 6/18 | 0/6 |
| v4_original | B | 6/18 | 4/6 |
| v4_original | C | 6/18 | 3/6 |
| v4_original | C2 | 6/18 | 2/6 |
| v4_original | P | 6/18 | 6/6 |
| v4_original | S | 6/18 | 3/6 |
| v3_replication | B | 0/15 | 0/0 |
| v3_replication | C | 0/15 | 0/0 |
| v3_replication | C2 | 15/15 | 9/15 |
| v4_replication | B | 2/6 | 1/2 |
| v4_replication | C2 | 2/6 | 1/2 |
| v4_replication | P | 2/6 | 1/2 |

## 실패 궤적

기존 main-002의 events-E1-L3-C2-r1. trace items[10–11]의 read_file 반환에 `report_timezone: Asia/Seoul`이 있다. 이후 items[19]의 Python 코드가 `day=row['ts_utc'][:10]`으로 UTC 날짜를 잘라 쓰고, items[25]에서 그 결과를 저장했다. 채점 이유는 `premise_from_other_env`. 한 사례의 메커니즘 예시이며, 빈도·인과 효과의 추정이 아니다.

## 남은 구현과 다음 실험

CARD.md 최종 설계의 N·V 조건, 일반화한 C2 문구, SkillsBench Hidden 변형, 통제 과제 Docker 포팅, verifier 사전 의존성 설치·오프라인 실행, 재개 기능, 전체 스킬 폴더 해시, 실패 테스트 이름 기록 등이 남아 있다. 이번 작업은 기존 실행기를 사용한 독립 재현이며 이 구현을 완료했다고 주장하지 않는다. 최종 본실험 700회의 예상 비용은 약 $26으로 이번 $10 승인 범위에 들어가지 않는다.

## 출처와 재현

- [W6·W7 발표 안내](https://app.notion.com/p/40f780c0050b81fea0a6d137a7a9d799): 11/10 21:00, 장현서 4번째, 장표 마감 20:00.
- [개인 설계 노션](https://app.notion.com/p/3f7780c0050b816b937bed1bc6bdc27d): 이전 파일럿과 최종 설계.
- [SkillsBench](https://arxiv.org/abs/2602.12670), [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401), [Demystifying Agent Skills](https://arxiv.org/abs/2608.14036). SWE-Skills-Bench는 2026-10-27 v2로 개정되어, 노션의 이전 49개 스킬 수치를 현재 논문 수치로 재사용하지 않았다.
- [모델 단가](https://developers.openai.com/api/docs/models/gpt-5.4-mini): 2026-11-09 확인.
- 로컬 기준 Agentproof@1095fba26ba6a66056eee4cc2c3b1e8f27f94adf. 실행 manifest의 코드·문구·스킬 해시 참조.

집계와 장표 재생성(API 호출 없음):

```sh
cd experiments/E02-skill-precheck
python3 src/w6_report.py
python3 presentation/w6/build_report.py
python3 presentation/w6/build_deck.py
```

API 재실행은 별도 명시적 승인 뒤 새 run-id로만 수행한다. 실행 계획은 `configs/plan_w6_replication.json`, `sb/plan_w6_replication.json`에 있다.

## 전체 셀

| 실행 | 과제/환경/위치/조건 | 성공 | 오류 | 비용($) |
|---|---|---:|---:|---:|
| v3_original | csv/E0/L2/A | 5/5 | 0 | 0.027678 |
| v3_original | csv/E0/L2/B | 5/5 | 0 | 0.031888 |
| v3_original | csv/E0/L2/C | 5/5 | 0 | 0.036811 |
| v3_original | csv/E0/L2/C2 | 5/5 | 0 | 0.045754 |
| v3_original | csv/E0/L3/A | 2/5 | 0 | 0.025967 |
| v3_original | csv/E0/L3/B | 5/5 | 0 | 0.027823 |
| v3_original | csv/E0/L3/C | 5/5 | 0 | 0.029321 |
| v3_original | csv/E0/L3/C2 | 5/5 | 0 | 0.047638 |
| v3_original | csv/E1/L2/A | 5/5 | 0 | 0.030405 |
| v3_original | csv/E1/L2/B | 5/5 | 0 | 0.038856 |
| v3_original | csv/E1/L2/C | 5/5 | 0 | 0.040915 |
| v3_original | csv/E1/L2/C2 | 5/5 | 0 | 0.046269 |
| v3_original | csv/E1/L3/A | 1/5 | 0 | 0.023863 |
| v3_original | csv/E1/L3/B | 0/5 | 0 | 0.027931 |
| v3_original | csv/E1/L3/C | 0/5 | 0 | 0.030004 |
| v3_original | csv/E1/L3/C2 | 4/5 | 0 | 0.045280 |
| v3_original | events/E0/L2/A | 5/5 | 0 | 0.040198 |
| v3_original | events/E0/L2/B | 5/5 | 0 | 0.047448 |
| v3_original | events/E0/L2/C | 4/5 | 0 | 0.046135 |
| v3_original | events/E0/L2/C2 | 5/5 | 0 | 0.051347 |
| v3_original | events/E0/L3/A | 5/5 | 0 | 0.032767 |
| v3_original | events/E0/L3/B | 5/5 | 0 | 0.034810 |
| v3_original | events/E0/L3/C | 4/5 | 0 | 0.037240 |
| v3_original | events/E0/L3/C2 | 5/5 | 0 | 0.052746 |
| v3_original | events/E1/L2/A | 5/5 | 0 | 0.044715 |
| v3_original | events/E1/L2/B | 5/5 | 0 | 0.053921 |
| v3_original | events/E1/L2/C | 5/5 | 0 | 0.061483 |
| v3_original | events/E1/L2/C2 | 3/5 | 0 | 0.074397 |
| v3_original | events/E1/L3/A | 0/5 | 0 | 0.034762 |
| v3_original | events/E1/L3/B | 0/5 | 0 | 0.039590 |
| v3_original | events/E1/L3/C | 0/5 | 0 | 0.036872 |
| v3_original | events/E1/L3/C2 | 0/5 | 0 | 0.053490 |
| v3_original | graph/E0/L2/A | 5/5 | 0 | 0.042084 |
| v3_original | graph/E0/L2/B | 5/5 | 0 | 0.061131 |
| v3_original | graph/E0/L2/C | 5/5 | 0 | 0.063539 |
| v3_original | graph/E0/L2/C2 | 5/5 | 0 | 0.072352 |
| v3_original | graph/E0/L3/A | 0/5 | 0 | 0.037211 |
| v3_original | graph/E0/L3/B | 5/5 | 0 | 0.050840 |
| v3_original | graph/E0/L3/C | 4/5 | 0 | 0.048389 |
| v3_original | graph/E0/L3/C2 | 5/5 | 0 | 0.078492 |
| v3_original | graph/E1/L2/A | 5/5 | 0 | 0.041485 |
| v3_original | graph/E1/L2/B | 5/5 | 0 | 0.054374 |
| v3_original | graph/E1/L2/C | 5/5 | 0 | 0.062613 |
| v3_original | graph/E1/L2/C2 | 5/5 | 0 | 0.076183 |
| v3_original | graph/E1/L3/A | 5/5 | 0 | 0.038748 |
| v3_original | graph/E1/L3/B | 0/5 | 0 | 0.050523 |
| v3_original | graph/E1/L3/C | 0/5 | 0 | 0.049847 |
| v3_original | graph/E1/L3/C2 | 5/5 | 0 | 0.065380 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/A | 1/3 | 0 | 0.041094 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/B | 3/3 | 0 | 0.141505 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/C | 3/3 | 0 | 0.182370 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/C2 | 3/3 | 0 | 0.188409 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/P | 3/3 | 0 | 0.209914 |
| v4_original | crystallographic-wyckoff-position-analysis/E0/native/S | 3/3 | 0 | 0.153278 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/A | 1/3 | 0 | 0.104697 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/B | 3/3 | 0 | 0.143729 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/C | 3/3 | 0 | 0.170002 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/C2 | 3/3 | 0 | 0.156966 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/P | 2/3 | 1 | 0.175878 |
| v4_original | crystallographic-wyckoff-position-analysis/E1/native/S | 3/3 | 0 | 0.167062 |
| v4_original | dapt-intrusion-detection/E0/native/A | 0/3 | 1 | 0.075694 |
| v4_original | dapt-intrusion-detection/E0/native/B | 3/3 | 0 | 0.151253 |
| v4_original | dapt-intrusion-detection/E0/native/C | 2/3 | 1 | 0.097882 |
| v4_original | dapt-intrusion-detection/E0/native/C2 | 3/3 | 0 | 0.162176 |
| v4_original | dapt-intrusion-detection/E0/native/P | 2/3 | 1 | 0.148017 |
| v4_original | dapt-intrusion-detection/E0/native/S | 3/3 | 0 | 0.130914 |
| v4_original | dapt-intrusion-detection/E1/native/A | 0/3 | 1 | 0.150349 |
| v4_original | dapt-intrusion-detection/E1/native/B | 2/3 | 0 | 0.124508 |
| v4_original | dapt-intrusion-detection/E1/native/C | 3/3 | 0 | 0.158015 |
| v4_original | dapt-intrusion-detection/E1/native/C2 | 1/3 | 0 | 0.122505 |
| v4_original | dapt-intrusion-detection/E1/native/P | 2/3 | 0 | 0.182003 |
| v4_original | dapt-intrusion-detection/E1/native/S | 3/3 | 0 | 0.163267 |
| v4_original | econ-detrending-correlation/E0/native/A | 1/3 | 0 | 0.267060 |
| v4_original | econ-detrending-correlation/E0/native/B | 1/3 | 0 | 0.203462 |
| v4_original | econ-detrending-correlation/E0/native/C | 2/3 | 0 | 0.151952 |
| v4_original | econ-detrending-correlation/E0/native/C2 | 0/3 | 0 | 0.208147 |
| v4_original | econ-detrending-correlation/E0/native/P | 2/3 | 0 | 0.176662 |
| v4_original | econ-detrending-correlation/E0/native/S | 1/3 | 0 | 0.182382 |
| v4_original | econ-detrending-correlation/E1/native/A | 2/3 | 0 | 0.132289 |
| v4_original | econ-detrending-correlation/E1/native/B | 2/3 | 0 | 0.153206 |
| v4_original | econ-detrending-correlation/E1/native/C | 3/3 | 0 | 0.253988 |
| v4_original | econ-detrending-correlation/E1/native/C2 | 3/3 | 0 | 0.188546 |
| v4_original | econ-detrending-correlation/E1/native/P | 3/3 | 0 | 0.180027 |
| v4_original | econ-detrending-correlation/E1/native/S | 1/3 | 0 | 0.190982 |
| v4_original | llm-prefix-cache-replay/E0/native/A | 0/3 | 0 | 0.047776 |
| v4_original | llm-prefix-cache-replay/E0/native/B | 3/3 | 0 | 0.092880 |
| v4_original | llm-prefix-cache-replay/E0/native/C | 3/3 | 0 | 0.076098 |
| v4_original | llm-prefix-cache-replay/E0/native/C2 | 3/3 | 0 | 0.158026 |
| v4_original | llm-prefix-cache-replay/E0/native/P | 2/3 | 0 | 0.166307 |
| v4_original | llm-prefix-cache-replay/E0/native/S | 2/3 | 0 | 0.120341 |
| v4_original | llm-prefix-cache-replay/E1/native/A | 0/3 | 0 | 0.066774 |
| v4_original | llm-prefix-cache-replay/E1/native/B | 2/3 | 0 | 0.115560 |
| v4_original | llm-prefix-cache-replay/E1/native/C | 3/3 | 0 | 0.141326 |
| v4_original | llm-prefix-cache-replay/E1/native/C2 | 1/3 | 0 | 0.219184 |
| v4_original | llm-prefix-cache-replay/E1/native/P | 3/3 | 0 | 0.263602 |
| v4_original | llm-prefix-cache-replay/E1/native/S | 2/3 | 0 | 0.110860 |
| v4_original | r2r-mpc-control/E0/native/A | 1/3 | 0 | 0.141008 |
| v4_original | r2r-mpc-control/E0/native/B | 0/3 | 0 | 0.148401 |
| v4_original | r2r-mpc-control/E0/native/C | 1/3 | 0 | 0.216371 |
| v4_original | r2r-mpc-control/E0/native/C2 | 0/3 | 0 | 0.178317 |
| v4_original | r2r-mpc-control/E0/native/P | 1/3 | 0 | 0.249676 |
| v4_original | r2r-mpc-control/E0/native/S | 2/3 | 0 | 0.553479 |
| v4_original | r2r-mpc-control/E1/native/A | 0/3 | 0 | 0.115871 |
| v4_original | r2r-mpc-control/E1/native/B | 2/3 | 0 | 0.279559 |
| v4_original | r2r-mpc-control/E1/native/C | 0/3 | 0 | 0.139296 |
| v4_original | r2r-mpc-control/E1/native/C2 | 1/3 | 0 | 0.171351 |
| v4_original | r2r-mpc-control/E1/native/P | 3/3 | 0 | 0.236968 |
| v4_original | r2r-mpc-control/E1/native/S | 1/3 | 0 | 0.132684 |
| v4_original | threejs-to-obj/E0/native/A | 0/3 | 0 | 0.054247 |
| v4_original | threejs-to-obj/E0/native/B | 1/3 | 0 | 0.053813 |
| v4_original | threejs-to-obj/E0/native/C | 2/3 | 0 | 0.066425 |
| v4_original | threejs-to-obj/E0/native/C2 | 2/3 | 0 | 0.064176 |
| v4_original | threejs-to-obj/E0/native/P | 3/3 | 0 | 0.107294 |
| v4_original | threejs-to-obj/E0/native/S | 2/3 | 0 | 0.053079 |
| v4_original | threejs-to-obj/E1/native/A | 0/3 | 0 | 0.054857 |
| v4_original | threejs-to-obj/E1/native/B | 2/3 | 0 | 0.064765 |
| v4_original | threejs-to-obj/E1/native/C | 2/3 | 0 | 0.066124 |
| v4_original | threejs-to-obj/E1/native/C2 | 3/3 | 0 | 0.069416 |
| v4_original | threejs-to-obj/E1/native/P | 3/3 | 0 | 0.090424 |
| v4_original | threejs-to-obj/E1/native/S | 0/3 | 0 | 0.065476 |
| v3_replication | csv/E0/L2/B | 5/5 | 0 | 0.035094 |
| v3_replication | csv/E0/L2/C | 5/5 | 0 | 0.043175 |
| v3_replication | csv/E0/L2/C2 | 5/5 | 0 | 0.045983 |
| v3_replication | csv/E0/L3/B | 5/5 | 0 | 0.027443 |
| v3_replication | csv/E0/L3/C | 5/5 | 0 | 0.028825 |
| v3_replication | csv/E0/L3/C2 | 5/5 | 0 | 0.047329 |
| v3_replication | csv/E1/L2/B | 5/5 | 0 | 0.033519 |
| v3_replication | csv/E1/L2/C | 5/5 | 0 | 0.039931 |
| v3_replication | csv/E1/L2/C2 | 5/5 | 0 | 0.047220 |
| v3_replication | csv/E1/L3/B | 0/5 | 0 | 0.027376 |
| v3_replication | csv/E1/L3/C | 0/5 | 0 | 0.029522 |
| v3_replication | csv/E1/L3/C2 | 4/5 | 0 | 0.049668 |
| v3_replication | events/E0/L2/B | 5/5 | 0 | 0.045585 |
| v3_replication | events/E0/L2/C | 4/5 | 0 | 0.053982 |
| v3_replication | events/E0/L2/C2 | 5/5 | 0 | 0.055123 |
| v3_replication | events/E0/L3/B | 5/5 | 0 | 0.032823 |
| v3_replication | events/E0/L3/C | 5/5 | 0 | 0.041306 |
| v3_replication | events/E0/L3/C2 | 5/5 | 0 | 0.056185 |
| v3_replication | events/E1/L2/B | 5/5 | 0 | 0.056138 |
| v3_replication | events/E1/L2/C | 5/5 | 0 | 0.060490 |
| v3_replication | events/E1/L2/C2 | 3/5 | 0 | 0.080642 |
| v3_replication | events/E1/L3/B | 0/5 | 0 | 0.032752 |
| v3_replication | events/E1/L3/C | 0/5 | 0 | 0.045853 |
| v3_replication | events/E1/L3/C2 | 0/5 | 0 | 0.052840 |
| v3_replication | graph/E0/L2/B | 5/5 | 0 | 0.052047 |
| v3_replication | graph/E0/L2/C | 5/5 | 0 | 0.061609 |
| v3_replication | graph/E0/L2/C2 | 5/5 | 0 | 0.071477 |
| v3_replication | graph/E0/L3/B | 5/5 | 0 | 0.052580 |
| v3_replication | graph/E0/L3/C | 5/5 | 0 | 0.056563 |
| v3_replication | graph/E0/L3/C2 | 5/5 | 0 | 0.074083 |
| v3_replication | graph/E1/L2/B | 5/5 | 0 | 0.062057 |
| v3_replication | graph/E1/L2/C | 5/5 | 0 | 0.062576 |
| v3_replication | graph/E1/L2/C2 | 5/5 | 0 | 0.072605 |
| v3_replication | graph/E1/L3/B | 0/5 | 0 | 0.045583 |
| v3_replication | graph/E1/L3/C | 0/5 | 0 | 0.048360 |
| v3_replication | graph/E1/L3/C2 | 5/5 | 0 | 0.069917 |
| v4_replication | crystallographic-wyckoff-position-analysis/E0/native/B | 1/1 | 0 | 0.047759 |
| v4_replication | crystallographic-wyckoff-position-analysis/E0/native/C2 | 1/1 | 0 | 0.060247 |
| v4_replication | crystallographic-wyckoff-position-analysis/E0/native/P | 1/1 | 0 | 0.092786 |
| v4_replication | crystallographic-wyckoff-position-analysis/E1/native/B | 1/1 | 0 | 0.056369 |
| v4_replication | crystallographic-wyckoff-position-analysis/E1/native/C2 | 1/1 | 0 | 0.061033 |
| v4_replication | crystallographic-wyckoff-position-analysis/E1/native/P | 1/1 | 0 | 0.058903 |
| v4_replication | dapt-intrusion-detection/E1/native/B | 1/1 | 0 | 0.039349 |
| v4_replication | dapt-intrusion-detection/E1/native/C2 | 1/1 | 0 | 0.059779 |
| v4_replication | dapt-intrusion-detection/E1/native/P | 0/1 | 0 | 0.082706 |
| v4_replication | econ-detrending-correlation/E0/native/B | 0/1 | 0 | 0.055931 |
| v4_replication | econ-detrending-correlation/E0/native/C2 | 1/1 | 0 | 0.059320 |
| v4_replication | econ-detrending-correlation/E0/native/P | 0/1 | 0 | 0.041940 |
| v4_replication | econ-detrending-correlation/E1/native/B | 1/1 | 0 | 0.050675 |
| v4_replication | econ-detrending-correlation/E1/native/C2 | 0/1 | 0 | 0.081019 |
| v4_replication | econ-detrending-correlation/E1/native/P | 1/1 | 0 | 0.084226 |
| v4_replication | llm-prefix-cache-replay/E0/native/B | 1/1 | 0 | 0.051787 |
| v4_replication | llm-prefix-cache-replay/E0/native/C2 | 1/1 | 0 | 0.052896 |
| v4_replication | llm-prefix-cache-replay/E0/native/P | 1/1 | 0 | 0.089911 |
| v4_replication | llm-prefix-cache-replay/E1/native/B | 1/1 | 0 | 0.062950 |
| v4_replication | llm-prefix-cache-replay/E1/native/C2 | 1/1 | 0 | 0.051860 |
| v4_replication | llm-prefix-cache-replay/E1/native/P | 1/1 | 0 | 0.091241 |
| v4_replication | r2r-mpc-control/E0/native/B | 0/1 | 0 | 0.090434 |
| v4_replication | r2r-mpc-control/E0/native/C2 | 1/1 | 0 | 0.104763 |
| v4_replication | r2r-mpc-control/E0/native/P | 0/1 | 0 | 0.054627 |
| v4_replication | r2r-mpc-control/E1/native/B | 0/1 | 0 | 0.089537 |
| v4_replication | r2r-mpc-control/E1/native/C2 | 0/1 | 0 | 0.099961 |
| v4_replication | r2r-mpc-control/E1/native/P | 0/1 | 0 | 0.133082 |
| v4_replication | threejs-to-obj/E0/native/B | 1/1 | 0 | 0.017101 |
| v4_replication | threejs-to-obj/E0/native/C2 | 1/1 | 0 | 0.021464 |
| v4_replication | threejs-to-obj/E0/native/P | 1/1 | 0 | 0.031244 |
| v4_replication | threejs-to-obj/E1/native/B | 1/1 | 0 | 0.017068 |
| v4_replication | threejs-to-obj/E1/native/C2 | 0/1 | 0 | 0.023929 |
| v4_replication | threejs-to-obj/E1/native/P | 1/1 | 0 | 0.036758 |
