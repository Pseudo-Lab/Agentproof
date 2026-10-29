# E01 실행 안내: 도구 출력 압축 실험

설계와 결론은 [CARD.md](CARD.md), 공통 절차는 [제출 안내](../../docs/SUBMISSION_GUIDE.md).

## 구조

- 에이전트 루프, 명령 실행, 응답 파싱, 프롬프트는 **mini-swe-agent 2.4.6** 의 것을 그대로 쓴다
  (`DefaultAgent` + `LocalEnvironment`, 텍스트 모드 설정 `minisweagent/config/mini_textbased.yaml` 의 템플릿).
- 개입은 `src/mini_compress.py` 한 곳이다. mini 의 텍스트 모드 모델 클래스를 상속해 `query()` 직전에
  `compress_old_observations()` 를 적용한다. baseline 은 같은 클래스를 `compression_enabled=false` 로 쓴다.
- 압축 함수, 과제 작업 디렉터리, 숨겨진 테스트 채점, 반복 탐지는 `src/agent_core.py`.
- 실행 순서, 로그 규격(manifest / trials.jsonl / summary.json), 궤적 저장은 `src/run.py`.

## 필요한 것

- Python 3.10 이상.
- `pip install -r requirements.txt` (mini-swe-agent 2.4.6 과 그 의존성 litellm, pyyaml). 채점기와 단위 테스트는 표준 라이브러리만 쓴다.
- 실제 실행(`--mode real`)에만: [Ollama](https://ollama.com) **0.30 이상**과 모델 `qwen3.5:9b-q4_K_M` (6.6GB, 다이제스트 `56671c2ab938`). 0.2x 에서는 이 모델을 받을 수 없다(412). macOS 에서 Ollama.app 과 brew 포뮬러가 둘 다 있으면 `which -a ollama` 로 어느 것이 서버인지 확인한다.
- 과제 재생성(`src/prepare_tasks.py`)에만: `pyarrow`.

환경 변수 (이름만, 값은 커밋하지 않음):

| 이름 | 용도 | 기본값 |
| --- | --- | --- |
| `OLLAMA_HOST` | Ollama 서버 주소 (litellm `api_base` 로 전달) | `http://127.0.0.1:11434` |
| `MSWEA_COST_TRACKING` | mini 의 비용 계산 오류 무시. 실행기가 `ignore_errors` 로 자동 설정 | `ignore_errors` |
| `MSWEA_SILENT_STARTUP` | mini 시작 배너 끄기. 실행기가 자동 설정 | `1` |

API 키는 필요 없다.

## 1. 오프라인 검증 (모델 호출 없음)

레포 루트에서 실행한다. 아래는 레포 루트에 `.venv` 를 만든 경우다.

```sh
python3 -m venv .venv && .venv/bin/pip install -r experiments/E01-tool-output-compression/requirements.txt

# 단위 테스트: 압축 함수(mini 관찰 메시지 형식 기준), 채점기(정답·오답·문법 오류·변조·파일 삭제)
.venv/bin/python -m unittest discover -s experiments/E01-tool-output-compression/tests

# mock 모드: mini 의 DeterministicModel 에 고정 응답을 넣어 과제 3개 × 2회를 돌리고 로그 규격과 집계기를 확인
.venv/bin/python experiments/E01-tool-output-compression/src/run.py --run-id mock-check-001 --mode mock --limit-tasks 3 --repeats 2
.venv/bin/python harness/summarize.py experiments/E01-tool-output-compression/results/pilot/mock-check-001
```

mock 응답은 사람이 쓴 fixture 다. intervention 만 정답을 쓰도록 되어 있으므로 성공률 차이는 개입 효과가 아니다. mock 결과는 제출하지 않는다.

## 2. 과제 준비

`data/tasks.json` 은 이미 들어 있다(파일럿 10개, seed 20261026). 다시 만들려면:

```sh
curl -L -o /tmp/humanevalpack-python.parquet \
  https://huggingface.co/datasets/bigcode/humanevalpack/resolve/main/python/test-00000-of-00001.parquet
python3 experiments/E01-tool-output-compression/src/prepare_tasks.py \
  --source /tmp/humanevalpack-python.parquet --split pilot --n 10 --seed 20261026
```

본 실험 과제(파일럿 제외 30개)는 파일럿 뒤에 `--split main --n 30 --seed <새 값> --exclude data/tasks.json` 으로 만든다.

## 3. 실제 실행

```sh
ollama serve                              # 다른 터미널
ollama pull qwen3.5:9b-q4_K_M
ollama list | grep qwen3.5                # 다이제스트 확인

# 1건 실측 (과제 1개 × 2조건 × 1회)
.venv/bin/python experiments/E01-tool-output-compression/src/run.py --run-id probe-001 --mode real --limit-tasks 1 --repeats 1

# 파일럿: 10과제 × 2조건 × 5회 = 100시도
.venv/bin/python experiments/E01-tool-output-compression/src/run.py --run-id pilot-001 --mode real --stage pilot

# 중단됐으면 같은 run-id 로 이어서 (끝난 시도는 건너뜀)
.venv/bin/python experiments/E01-tool-output-compression/src/run.py --run-id pilot-001 --mode real --stage pilot --resume

# 로그 검증과 요약
.venv/bin/python harness/summarize.py experiments/E01-tool-output-compression/results/pilot/pilot-001
```

모델 호출은 `--mode real` 에서 mini 의 `LitellmTextbasedModel.query()` 가 불릴 때만 일어난다. 비용은 로컬 추론이라 0 이며 `cost_usd` 는 null 과 이유로 기록된다. 토큰은 litellm 이 돌려 주는 usage(Ollama 의 `prompt_eval_count` / `eval_count`)를 합산한다.

## 3순위 묶음: SWE-bench Lite (Docker 필요)

```sh
# 과제 선정 (원본 jsonl 과 Verified id 목록은 datasets 로 받아 둔다. 자세한 규칙은 스크립트 docstring)
python3 experiments/E01-tool-output-compression/src/prepare_swebench.py --source <lite_test.jsonl> \
  --verified-ids <verified_ids.json> --n 10 --seed 20261029 \
  --out experiments/E01-tool-output-compression/data/tasks_swebench_pilot.json

# 채점 가능성 검증: 과제마다 정답 패치 → resolved, 주석만 붙인 패치 → unresolved 여야 쓴다
.venv/bin/python experiments/E01-tool-output-compression/src/validate_swebench.py \
  --tasks experiments/E01-tool-output-compression/data/tasks_swebench_pilot.json \
  --out experiments/E01-tool-output-compression/results/pilot/swebench-validation.json

# 실행 (과제 이미지는 linux/amd64 로 받는다. Apple Silicon 에서는 Rosetta 에뮬레이션)
.venv/bin/python experiments/E01-tool-output-compression/src/run.py --run-id swe-r1-001 --mode real \
  --tasks experiments/E01-tool-output-compression/data/tasks_swebench_pilot.json --repeats 1
```

에이전트는 mini 의 `DockerEnvironment` 와 SWE-bench 텍스트 모드 템플릿(`config/benchmarks/swebench_backticks.yaml`)으로 돈다. 채점은 SWE-bench 공식 하네스가 새 컨테이너에서 제출 패치만 적용해 숨겨진 테스트로 한다. 과제 이미지 10개는 합계 수십 GB 다.

## 산출물

```
results/<stage>/<run-id>/
  manifest.json      실험 ID, 모드, commit, 모델, mini 버전, 설정 전문, 과제 목록, 데이터 체크섬, 실행 순서, seed 정책
  trials.jsonl       시도당 한 줄 (harness/schemas/trial.schema.json 규격)
  summary.json       harness/summarize.py 결과
  trajectories/<task>/<condition>/repeat-N.json
                     mini 궤적 형식(mini-swe-agent-1.1) 그대로: 전체 메시지(압축 전 원문), 턴별 extra 에
                     압축 통계와 litellm 응답(usage 포함). e01 키 아래에 채점 결과, 최종 저장소 스냅샷, seed.
```

trial 한 줄의 `evidence` 에는 종료 사유(mini 의 exit_status: Submitted / LimitsExceeded / TimeExceeded / RepeatedFormatError / ContextOverflow), 턴 수, seed, 압축 작동 여부와 수치, 도구 출력 수, 반복 탐지, 채점 근거가 들어간다.

## 실행 순서와 재시도 정책

반복 회차 → 과제 → (baseline, intervention) 순으로 교차 실행한다. mini 가 처리하지 못한 예외(모델 서버 다운 등)는 `status=error` 로 행을 남긴다. 다시 돌릴 때는 해당 행을 `trials.jsonl` 에서 지우고 `--resume` 으로 그 시도만 재실행하며, 지운 행과 이유를 CARD 에 적는다.

## 두 조건의 차이 확인

```sh
diff <(python3 -c "import json;d=json.load(open('experiments/E01-tool-output-compression/configs/baseline.json'));d.pop('condition');d.pop('compression');print(json.dumps(d,sort_keys=True))") \
     <(python3 -c "import json;d=json.load(open('experiments/E01-tool-output-compression/configs/intervention.json'));d.pop('condition');d.pop('compression');print(json.dumps(d,sort_keys=True))") \
  && echo "compression 외 동일"
```

`run.py` 도 시작할 때 같은 검사를 하고, 다르면 실행을 거부한다.
