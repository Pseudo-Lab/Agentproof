# E03 — mini-swe-agent 기반 S/U/E 파일럿

[mini-swe-agent 2.4.6](https://github.com/SWE-agent/mini-swe-agent/tree/04d809ceab9df28f9adaed044884180159172930)을 기반으로
검색(S)·읽기(U)·편집(E) 도구가 해결률과 효율에 미치는 영향을 비교한다.
실행 루프와 배치 runner는 mini를 사용하고, 검색은 AutoCodeRover, 읽기·편집은 CodeStruct를 연결한다.

[설계·결과](CARD.md) · [실패 사례](FAILURES.md) · [원본 버전](configs/upstreams.lock.json)

```text
src/minisweagent/    mini 에이전트·모델·환경·runner·설정
tools/              S/U/E 도구
tests/aci/          연동 검사
environments/serve/ vLLM 환경
data/               문제와 공식 평가 입력
results/            실행 기록·공식 점수·요약
```

## 설치

Linux, Docker, uv, Python 3.12와 모델을 수용하는 GPU가 필요하다.
Agentproof 루트에서 시작한다.

```bash
cd experiments/E03-aci-sue
git clone https://github.com/SWE-bench/SWE-bench.git external/SWE-bench
git -C external/SWE-bench checkout --detach 726c5461e2ef52d83cf1ea2107870a8bb3328d57
uv sync --python 3.12 --locked --extra research
uv sync --python 3.12 --locked --project environments/serve
mkdir -p .cache/aci-bin
cp "$(command -v uv)" .cache/aci-bin/uv
```

## 실행

Gemma 가중치를 `models/gemma-4-31B-it`에 준비하고 서버를 실행한다.
revision은 `842da3794eaa0b77d5f08bae87a17459d91ff475`이다.

```bash
env -u CUDA_VISIBLE_DEVICES VLLM_CACHE_ROOT="$PWD/.cache/vllm-gpu2" \
  uv run --no-sync --project environments/serve vllm serve models/gemma-4-31B-it \
  --config src/minisweagent/config/extra/serve-gemma31b.yaml --device-ids 2 --port 18002
```

별도 터미널에서 같은 실험 폴더로 이동한 뒤 실행한다.

```bash
export OPENAI_API_KEY=EMPTY
uv run --locked --extra research python -m minisweagent.run.benchmarks.aci \
  --subset data/agent --split test --workers 1 \
  -c swebench.yaml -c aci-common.yaml -c model-gemma4-31b.yaml \
  -c aci-baseline.yaml -c aci-tool-first.yaml -c endpoint-gpu2.yaml -c aci-wall600.yaml \
  -o results/reproduction-gemma-baseline
```

Qwen은 `model-qwen35-27b.yaml`, `endpoint-gpu3.yaml`, `serve-qwen35-27b.yaml`, GPU 3/port 18003을 사용한다.
가중치 경로는 `models/Qwen3.5-27B`, revision은 `fc05daec18b0a78c049392ed2e771dde82bdf654`이다.
문제당 600초이며 매번 새 출력 경로를 사용한다.

## 공식 평가

모든 제출 후 같은 실험 폴더에서 실행한다.

```bash
uv run --locked --extra research python -m swebench.harness.run_evaluation \
  --dataset_name data/evaluator/tasks.json \
  --predictions_path results/reproduction-gemma-baseline/preds.json \
  --run_id e03-gemma-baseline-reproduction --max_workers 2 --timeout 900
```

## 저장된 결과 확인

Agentproof 루트에서 실행한다. 로그는 일반 JSON/텍스트 파일이다.

```bash
python3 experiments/E03-aci-sue/src/export_trials.py
python3 experiments/E03-aci-sue/src/test_export.py
python3 harness/summarize.py experiments/E03-aci-sue/results/pilot/E03-gemma31b-historical-pilot5
python3 harness/summarize.py experiments/E03-aci-sue/results/pilot/E03-qwen27b-historical-pilot5
```

프롬프트·설정은 `configs/`, 모델 응답·도구 호출은 `results/pilot/`의 trajectory에서 확인한다.
호스트 경로는 익명화했다. mini와 도구의 LICENSE/NOTICE를 보존했으며 CodeStruct는 CC-BY-NC-4.0을 따른다.
