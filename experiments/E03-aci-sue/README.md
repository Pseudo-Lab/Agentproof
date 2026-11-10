# E03 — mini-swe-agent 기반 S/U/E 실험

mini-swe-agent의 bash baseline과 검색(S)·읽기(U)·편집(E) 전용 도구를 쓰는 변형을 비교한다.
[설계·파일럿 결과](CARD.md) · [실패 사례](FAILURES.md) · [원본 버전](configs/upstreams.lock.json)

mini-swe-agent는 아래 고정 commit을 **clone해서 사용**한다. 이 폴더에는 자체 실행 코드,
Base/SUE 설정, 도구 어댑터, SWE-bench Verified 고정 100문제만 둔다.
`results/`와 trajectory, 과거 데이터·부가 실험은 로컬 보관본에 남겼다.
CARD의 5문제 파일럿 결과는 현재 고정100의 결과가 아니다.

```text
src/e03_aci/         baseline·SUE 실행 코드
configs/            Base/SUE, 모델·서버 설정
tools/              AutoCodeRover 검색·CodeStruct 읽기/편집
tests/aci/          연동 검사
data/               고정100 데이터와 선택 메타데이터
environments/serve/ vLLM 환경
```

## 설치

Linux, Docker, uv, Python 3.12를 사용한다. Agentproof 루트에서 시작한다.
mini-swe-agent와 공식 채점기는 각각 아래 commit으로 고정한다.

```bash
cd experiments/E03-aci-sue
git clone https://github.com/SWE-agent/mini-swe-agent.git external/mini-swe-agent
git -C external/mini-swe-agent checkout --detach 04d809ceab9df28f9adaed044884180159172930
git clone https://github.com/SWE-bench/SWE-bench.git external/SWE-bench
git -C external/SWE-bench checkout --detach 726c5461e2ef52d83cf1ea2107870a8bb3328d57
uv sync --python 3.12 --locked --extra research
uv sync --python 3.12 --locked --project environments/serve
mkdir -p .cache/aci-bin
cp "$(command -v uv)" .cache/aci-bin/uv
```

`uv sync`는 clone한 mini-swe-agent와 이 폴더의 실행 코드를 함께 설치한다.
`external/`은 Git에서 제외한다. 아래 명령은 모두 이 실험 폴더에서 실행한다.

## 실행

Gemma 가중치를 `models/gemma-4-31B-it`에 준비한다.
사용한 revision은 `842da3794eaa0b77d5f08bae87a17459d91ff475`이다.

```bash
env -u CUDA_VISIBLE_DEVICES VLLM_CACHE_ROOT="$PWD/.cache/vllm-gpu2" \
  uv run --no-sync --project environments/serve vllm serve models/gemma-4-31B-it \
  --config configs/serve-gemma31b.yaml --device-ids 2 --port 18002
```

별도 터미널에서 같은 실험 폴더로 이동한 뒤 공통 환경변수를 설정한다.

```bash
export OPENAI_API_KEY=EMPTY
export MSWEA_CONFIG_DIR="$PWD/configs"
```

Base:

```bash
uv run --locked --extra research python -m e03_aci.aci \
  --subset data/agent --split test --workers 1 \
  -c swebench.yaml -c aci-common.yaml -c model-gemma4-31b.yaml \
  -c aci-baseline.yaml -c aci-tool-first.yaml -c endpoint-gpu2.yaml -c aci-wall600.yaml \
  -o results/gemma-baseline
```

SUE:

```bash
uv run --locked --extra research python -m e03_aci.aci_staged \
  --subset data/agent --split test --workers 1 \
  -c swebench.yaml -c aci-common.yaml -c model-gemma4-31b.yaml \
  -c aci-sue.yaml -c endpoint-gpu2.yaml -c aci-wall600.yaml -c aci-staged.yaml \
  -o results/gemma-sue
```

Qwen은 `model-qwen35-27b.yaml`, `endpoint-gpu3.yaml`, `serve-qwen35-27b.yaml`, GPU 3/port 18003을 사용한다.
가중치 경로는 `models/Qwen3.5-27B`, revision은 `fc05daec18b0a78c049392ed2e771dde82bdf654`이다.
문제당 600초이며 새 실행에는 새 출력 경로를 사용한다.

## 데이터와 공식 채점

고정100의 ID·순서·base commit은 [data/selection.json](data/selection.json)에 기록했다.
기존 입력 형식을 유지한다: 실행에는 `data/agent`, 채점에는 `data/evaluator/tasks.json`을 사용한다.

```bash
uv run --locked --extra research python -m swebench.harness.run_evaluation \
  --dataset_name data/evaluator/tasks.json \
  --predictions_path results/gemma-baseline/preds.json \
  --run_id e03-gemma-baseline --max_workers 2 --timeout 900
```

SUE 채점 시에는 `--predictions_path`와 `--run_id`를 해당 실행으로 바꾼다.

## 코드 검사

모델 호출이나 GPU 없이 설정 조합과 runner 진입점을 확인한다.

```bash
uv run --locked --extra research pytest -q tests/aci/test_configs.py
uv run --locked --extra research python -m e03_aci.aci --help
uv run --locked --extra research python -m e03_aci.aci_staged --help
```

도구 원본 대조 검사는 `configs/upstreams.lock.json`의 AutoCodeRover·CodeStruct를 `external/`에
준비하고, 설치된 도구 번들을 `ACI_TEST_BUNDLES`로 지정해야 한다.
Docker replay 검사는 `ACI_NATIVE_REPLAY=1`과 `aci-lens-smoke:mini-20261025` 이미지를 사용한다.

도구의 LICENSE/NOTICE와 UTF-8 수정 패치를 보존했다. CodeStruct는 CC-BY-NC-4.0을 따른다.
