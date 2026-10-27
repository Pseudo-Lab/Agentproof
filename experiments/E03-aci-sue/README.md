# E03 실행 안내

[연구 설계·결과](CARD.md) · [실패 분석](FAILURES.md) · [코드 출처](src/snapshots/README.md)

## 저장된 결과 검증

Agentproof 루트에서 Python 3.10+로 실행한다.

```bash
python3 experiments/E03-aci-sue/src/export_trials.py
python3 -m unittest discover -s experiments/E03-aci-sue/src -p 'test_*.py' -v
python3 harness/summarize.py experiments/E03-aci-sue/results/pilot/E03-gemma31b-historical-pilot5
python3 harness/summarize.py experiments/E03-aci-sue/results/pilot/E03-qwen27b-historical-pilot5
```

20개 trajectory의 해시·patch·공식 점수·usage와 summary를 대조한다.
파생 trials/summary 재생성은 `export_trials.py --write`로 실행한다.
전체 프롬프트·설정은 `configs/*.json`, 렌더링된 prompt·응답·tool call은 `*.traj.json.gz`에 있다.

## 실제 실행 재현

Linux, Docker, `uv`, Python 3.12, 모델을 수용하는 GPU, 공개 모델/이미지 접근이 필요하다.
당시 한 replica당 약 95GiB GPU 메모리를 사용 가능한 장치에서 실행했다.
모델 가중치는 포함하지 않는다. 제공자의 모델 이용 조건에 따라 아래 revision을 로컬 경로에 준비한다.

| 모델 | 공급자 ID | revision | snapshot 내 로컬 경로 |
| --- | --- | --- | --- |
| Gemma | `google/gemma-4-31B-it` | `842da3794eaa0b77d5f08bae87a17459d91ff475` | `models/gemma-4-31B-it` |
| Qwen | `Qwen/Qwen3.5-27B` | `fc05daec18b0a78c049392ed2e771dde82bdf654` | `models/Qwen3.5-27B` |

다음은 Gemma staged 예다. baseline은 **baseline archive**를 별도 폴더에 풀고 아래 표의 실행 차이를 적용한다.

```bash
# Agentproof 루트; E03_WORK는 아직 없는 새 경로를 선택한다.
E03_PACKAGE="$PWD/experiments/E03-aci-sue"
E03_WORK=/tmp/e03-gemma-staged-reproduction
mkdir "$E03_WORK"
tar -xzf "$E03_PACKAGE/src/snapshots/intervention.tar.gz" -C "$E03_WORK"
cp -R "$E03_PACKAGE/data" "$E03_WORK/data"
cd "$E03_WORK"
git clone https://github.com/SWE-bench/SWE-bench.git external/SWE-bench
git -C external/SWE-bench checkout --detach 726c5461e2ef52d83cf1ea2107870a8bb3328d57
uv sync --python 3.12 --locked --extra research
uv sync --python 3.12 --locked --project environments/serve
mkdir -p .cache/aci-bin
cp "$(command -v uv)" .cache/aci-bin/uv
```

도구는 기존 `run.env_startup_command`가 설치한다. 모델 가중치를 위 경로에 준비한 뒤 별도 터미널에서 서버를 실행한다.
GPU 2는 당시의 물리 장치 번호이며 자신의 사용 가능한 번호로 바꿀 수 있다. 다른 하드웨어 사용은 조건 차이로 기록한다.

```bash
cd "$E03_WORK"
env -u CUDA_VISIBLE_DEVICES VLLM_CACHE_ROOT="$PWD/.cache/vllm-physical-gpu2" \
  uv run --no-sync --project environments/serve vllm serve models/gemma-4-31B-it \
  --config src/minisweagent/config/extra/serve-gemma31b.yaml --device-ids 2 --port 18002
```

에이전트 터미널에서 실행한다. 환경 변수 이름은 `OPENAI_API_KEY`, `CUDA_VISIBLE_DEVICES`, `VLLM_CACHE_ROOT`다.
아래 `EMPTY`는 인증 없는 로컬 서버용 placeholder로 실제 키가 아니다. 외부 endpoint를 쓰면 해당 인증과 비용 조건을 별도로 기록해야 한다.

```bash
cd "$E03_WORK"
export OPENAI_API_KEY=EMPTY
uv run --locked --extra research python -m minisweagent.run.benchmarks.aci_staged \
  --subset data/agent --split test --workers 1 \
  -c swebench.yaml -c aci-common.yaml -c model-gemma4-31b.yaml \
  -c aci-sue.yaml -c endpoint-gpu2.yaml -c aci-wall600.yaml -c aci-staged.yaml \
  -o results/reproduction-gemma-staged
```

| 변경 대상 | baseline | Qwen |
| --- | --- | --- |
| 실행 module | `minisweagent.run.benchmarks.aci` | 조건별 module 유지 |
| 조건 설정 | `aci-sue.yaml` → `aci-baseline.yaml`; `aci-staged.yaml` 제거; model/condition 뒤 `aci-tool-first.yaml` 추가 | 조건 설정 유지 |
| 모델·endpoint | Gemma 유지 | `model-qwen35-27b.yaml`, `endpoint-gpu3.yaml` |
| 서버 | Gemma 유지 | `models/Qwen3.5-27B`, `serve-qwen35-27b.yaml`, GPU 3, port 18003, 별도 cache |
| 출력 | 매번 새 경로 | 매번 새 경로 |

정확한 원래 인자 순서는 `configs/*-commands.json`에 있다. 그 기록의 호스트 경로는 `/workspace/aci-lens`로 익명화했다.
원래 입력은 50개 파일에 `--filter`로 이 5개를 선택했다. 위 명령은 동일한 5개 입력만 담은 공개 파일을 사용한다.
mini는 기존 `preds.json`의 문제를 건너뛰므로 새 출력 경로를 사용한다.
한 모델·조건은 최대 5×600초의 agent 시간과 준비/회수/채점 시간이 든다. 4배치는 최대 200분의 agent 시간이다.
로컬 GPU의 USD 비용은 미측정이며, 검증 명령 자체에는 모델 호출이 없다.

모든 제출이 끝난 뒤 모델 서버를 종료하고 원본 evaluator를 실행한다. staged Gemma 예:

```bash
cd "$E03_WORK"
mkdir -p results/reproduction-gemma-staged/evaluation
cd results/reproduction-gemma-staged/evaluation
"$E03_WORK/.venv/bin/python" -m swebench.harness.run_evaluation \
  --dataset_name "$E03_WORK/data/evaluator/tasks.json" \
  --predictions_path "$E03_WORK/results/reproduction-gemma-staged/preds.json" \
  --run_id e03-gemma-staged-reproduction --max_workers 2 --timeout 900
```

`data/evaluator/`는 호스트의 채점 입력이다. agent Docker에는 도구 번들만 마운트하며 이 경로를 마운트하지 않는다.
900초는 공식 채점 timeout이고 agent의 600초 예산과 다르다.

## 공개 범위

공개 로그에서 호스트의 프로젝트 경로와 홈 경로를 `/workspace/aci-lens`, `/home/runner`로 치환했다.
원본/public SHA-256은 manifest에 있다. 공식 test output은 실패 부분의 줄 번호·해시·발췌를 제공한다.
모델 가중치·인증·개인 환경 파일은 제외했다. CodeStruct LICENSE/NOTICE와 CC-BY-NC-4.0 조건을 보존했다.
검증 명령은 실행했으며 모델 재실행·교차 재현은 다음 단계다.
