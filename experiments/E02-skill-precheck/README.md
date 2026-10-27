# E02 — 스킬 적용 전 확인 하네스

맞지 않을 수도 있는 스킬을 받은 에이전트에게, 스킬을 읽은 직후 "적용 전에 전제를 현재 과제·입력·환경과 대조하라"는
메시지를 한 번 넣으면 메시지가 없을 때(B)보다 최종 산출물 정답률이 오르는지 본다. 일반 확인 메시지(C)와 확인할 위치 유형을 알려주는 메시지(C2)를, 근거가 계약에 지시된 경우(L2)와 지시되지 않은 경우(L3)에서 비교한다(설계 v3). 설계와 결과는 [CARD.md](CARD.md).

## 요구 사항

- Python 3.10+ (표준 라이브러리만), `curl`
- 실제 실행 시 레포 루트 `.env`에 `OPENAI_API_KEY` (커밋 금지, `.gitignore`에 포함)

## 실행

레포 루트가 아니라 이 폴더에서 실행한다.

```sh
cd experiments/E02-skill-precheck

# 1) API 없이 채점기·조작 점검 (oracle 통과, 스킬 그대로 적용 시 E0 통과·E1 실패, 손상 출력 실패)
python3 src/check_graders.py > /dev/null && echo OK

# 2) API 없이 배관 점검 (scripted mock client — 결과로 쓰지 말 것)
python3 src/run.py --plan configs/plan_pilot_v3.json --run-id mock-001 --mock

# 3) 실제 실행 (유료). run-id는 매번 새로
python3 src/run.py --plan configs/plan_pilot_v3.json --run-id pilot-00X
python3 src/run.py --plan configs/plan_main.json --run-id main-001

# 4) 분석 다시 만들기 / 공통 요약 검증
python3 src/analyze.py results/<stage>/<run-id>
python3 ../../harness/summarize.py results/<stage>/<run-id>
```

## 구성

| 경로 | 내용 |
| --- | --- |
| `src/tasks.py` | 과제 3개 × E0/E1 × L2/L3 작업 공간 생성, 계약, 채점기, oracle/literal 참조 풀이 |
| `src/agent.py` | 도구 4개(read_skill, read_file, write_file, run_python) 단일 에이전트 루프, C/C2 확인 메시지 1회 삽입, 한도 |
| `src/openai_http.py` | Responses API 최소 클라이언트(curl, 자동 재시도 없음, 키는 stdin으로 전달) |
| `src/run.py` | plan 파일대로 실행, manifest·trials·trace·요약 기록 |
| `src/analyze.py` | 사전 등록 비교(P1·P2·S1·S2·M1), 칸별 성공 수, 근거 파일 열람 여부, 비용 |
| `src/check_graders.py` | API 없는 채점기·조작 점검 |
| `skills/` | 고정 스킬 3개 (graph·csv는 SkillsBench `f860ecf` 발췌, events는 자체 작성) |
| `configs/` | 모델·한도·단가, 조건 A/B/C/C2, 실행 계획 (`plan_pilot*.json`의 v1·v2 계획은 이전 코드용 기록) |
| `results/pilot/` | 파일럿 1차·2차 소규모 실행 기록 |
| `results/main/` | 파일럿 2차 확장 실행 기록 (폴더 이름은 실행 당시 기준) |
| `sb/`, `results/sb/` | 파일럿 3차(SkillsBench, Docker) 실행기와 기록. 최종 설계 본실험도 이 실행기를 쓴다 |

## 결과 파일

`results/<stage>/<run-id>/`

- `manifest.json`: 모델·한도·단가, 해시(스킬·프롬프트·도구·코드), 실행 순서, commit
- `trials_all.jsonl`: 모든 trial (A 포함, E02 필드)
- `trials.jsonl` / `summary.json`: B→baseline, C→intervention으로 옮긴 공통 규격과 공통 요약
- `analysis.json`: E02 분석
- `traces/<trial>/trace.json`, `traces/<trial>/output/`: 모델·도구 기록(암호화된 reasoning 제거)과 최종 산출물

## 알려진 차이·한계

- `run_python`은 임시 작업 공간에서 `python -I` 하위 프로세스로 실행하고 API 키를 포함한 사용자 환경 변수를 넘기지 않는다.
  설계의 "네트워크 없는 컨테이너"는 아직 아니다.
- 정답 파일은 디스크에 쓰지 않고 채점 시 seed로 다시 계산한다. 에이전트 도구 인자에 레포 경로가 나오면 `leak_flags`로 표시한다.
- graph·csv 스킬 발췌 출처: <https://github.com/benchflow-ai/skillsbench/tree/f860ecf02ef53412a030f8661c83d644b739ff01/tasks> (Apache-2.0).
  csv 발췌는 pandas/numpy 의존만 표준 라이브러리로 바꿨고, 원문의 "이 데이터셋에서 쉼표는 소수점" 주석은 그대로 뒀다.
