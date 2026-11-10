# E03 — mini-swe-agent 기반 S/U/E 실험

[mini-swe-agent 2.4.6](https://github.com/SWE-agent/mini-swe-agent/tree/04d809ceab9df28f9adaed044884180159172930)을 기반으로
검색(S)·읽기(U)·편집(E) 도구가 해결률과 효율에 미치는 영향을 비교한다.
실행 루프와 배치 runner는 mini를 사용하고, 검색은 AutoCodeRover, 읽기·편집은 CodeStruct를 연결한다.

[설계·결과](CARD.md) · [실패 사례](FAILURES.md) · [원본 버전](configs/upstreams.lock.json)

현재 실행 데이터는 **SWE-bench Verified에서 추출한 고정 100문제**로 통일했다.
실험 카드의 Lite 5문제·Verified Mini 10/50문제 결과는 과거 기록이며, 이 100문제의 결과가 아니다.
실행 결과 파일은 로컬에 보관하고, 이 PR에는 코드·설정·고정100 입력·문서의 핵심 결과만 포함한다.

```text
src/minisweagent/    mini 에이전트·모델·환경·runner·설정
tools/              S/U/E 도구
tests/aci/          연동 검사
environments/serve/ vLLM 환경
data/agent/         고정100 모델 입력 (정답 패치·채점 라벨 제외)
data/evaluator/     동일한 고정100의 공식 채점 입력
```

## 고정 100문제

[선택 메타데이터](src/minisweagent/config/datasets/swe-verified-heldout100-20261031.json)는
SWE-bench Verified revision `78f471bf655a3137b2e8a75af1501690ec009ec3`, 추출 seed
`20261031`, 문제 ID·순서·base commit을 고정한다. 추출 당시 개발에 노출되지 않은
문제에서 선택했으며, 이후 반복 사용한 같은 100문제다.

- 모델 실행: `data/agent/test.jsonl`에는 ID·저장소·base commit·문제 설명만 담았다.
- 공식 채점: `data/evaluator/tasks.json`에는 같은 100문제의 정답·테스트 정보를 담았다.

두 파일은 같은 문제 집합의 용도별 입력이다. 모델 실행에는 `data/agent`만 전달한다.
기존 Lite 및 Verified Mini 데이터와 결과는 로컬 보관본에 남겼다.

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

아래 명령은 고정100의 새 실행을 위한 예시다. 과거 5문제 파일럿을 재현하려면
해당 실행의 로컬 데이터·설정 보관본을 사용한다.

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

## 결과와 로컬 보관본

핵심 수치는 [실험 카드](CARD.md), 실패 패턴은 [실패 사례](FAILURES.md)에 남겼다.
`results/` 전체와 `*.traj.json`은 Git에서 제외한다. 원본 trajectory, 제출 patch,
공식 채점, 문제별 집계, manifest와 해시는 로컬 보관본에 유지한다.

`src/export_trials.py`는 과거 파일럿의 로컬 보관본을 대조하는 도구다.
실행하려면 해당 실행의 `results/`와 데이터·소스 보관본을 함께 복원해야 한다.
현재 PR만 받은 상태에서는 원로그 대조를 수행할 수 없다.
`python3 experiments/E03-aci-sue/src/test_export.py`의 합성 상태 매핑 검사는
원자료 없이 실행 가능하며, 실제 실험 결과의 검증을 대신하지 않는다.

mini와 도구의 LICENSE/NOTICE를 보존했으며 CodeStruct는 CC-BY-NC-4.0을 따른다.
