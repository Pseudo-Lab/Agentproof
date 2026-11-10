# E03 — SWE-agent · CodeStruct · SLACT 도구 구성

같은 mini-swe-agent 실행 루프에서 사용할 도구를 세 계열로 구분한다.
우리 방법의 문서·결과 표기는 **SLACT**이며, 자체 도구 폴더 이름은 요청한 `slcat/`을 사용한다.
[방법론과 과거 파일럿](CARD.md) · [외부 원본 버전](configs/upstreams.lock.json)

```text
tools/
├── swe-agent/edit/       SWE-agent의 창 단위 읽기·lint 편집
├── codestruct/
│   ├── reading/         CodeStruct readCode
│   └── editing/         CodeStruct editCode·str_replace·create_file
└── slcat/
    ├── search-grep/      기존 grep 결과의 코드 문맥 보강
    └── edit-diff/        수정 감지·관련 테스트 실행·검증 결과 전달
```

외부 도구는 원본 LICENSE/NOTICE와 수정 패치를 함께 보존한다. `slcat/`은 로컬 작업
버전의 검색·검증 구현이며, 기본 설정은 **G + V′**만 활성화한다. 파일에 포함된 후속
색인·편집 제한·실행 추적 기능은 기본 비교에서 활성화하지 않는다.
이 구조는 전체 SWE-agent/CodeStruct 에이전트와의 성능 비교를 뜻하지 않는다.

## 설치

Linux, Docker, uv, Python 3.12를 사용한다. Agentproof 루트에서 시작한다.
mini는 복사본을 포함하지 않고 고정 commit을 clone해서 사용한다.

```bash
cd experiments/E03-aci-sue
git clone https://github.com/SWE-agent/mini-swe-agent.git external/mini-swe-agent
git -C external/mini-swe-agent checkout --detach 04d809ceab9df28f9adaed044884180159172930
git clone https://github.com/SWE-bench/SWE-bench.git external/SWE-bench
git -C external/SWE-bench checkout --detach 726c5461e2ef52d83cf1ea2107870a8bb3328d57
git clone https://github.com/AutoCodeRoverSG/auto-code-rover.git external/auto-code-rover
git -C external/auto-code-rover checkout --detach 585d3e639aeda58ef0b6a151dd1cc2721a94d267
uv sync --python 3.12 --locked --extra research
uv sync --python 3.12 --locked --project environments/serve
mkdir -p .cache/aci-bin
cp "$(command -v uv)" .cache/aci-bin/uv
```

AutoCodeRover에서는 검색 보강에 필요한 Python 파싱 helper만 재사용한다.
`external/`, `results/`, trajectory는 Git에서 제외한다.

## 실행

아래 명령은 모두 이 실험 폴더에서 실행한다. Gemma 가중치는 `models/gemma-4-31B-it`에
준비한다. 설정에 사용한 revision은 `842da3794eaa0b77d5f08bae87a17459d91ff475`이다.

```bash
env -u CUDA_VISIBLE_DEVICES VLLM_CACHE_ROOT="$PWD/.cache/vllm-gpu2" \
  uv run --no-sync --project environments/serve vllm serve models/gemma-4-31B-it \
  --config configs/serve-gemma31b.yaml --device-ids 2 --port 18002
```

별도 터미널에서 조건 하나를 선택한다.

| `condition` | 동작 |
|---|---|
| `baseline` | 기존 bash 인터페이스 |
| `slcat` | 같은 프롬프트·도구에 검색 문맥과 자동 검증 피드백 추가 |
| `codestruct` | bash에서 CodeStruct 읽기·편집 명령 사용 |
| `swe-agent` | bash에서 SWE-agent 창 단위 읽기·lint 편집 명령 사용 |

```bash
export OPENAI_API_KEY=EMPTY
export MSWEA_CONFIG_DIR="$PWD/configs"
condition=slcat
uv run --locked --extra research python -m e03_aci.aci \
  --subset data/agent --split test --workers 1 \
  -c swebench.yaml -c aci-common.yaml -c model-gemma4-31b.yaml \
  -c "aci-$condition.yaml" -c endpoint-gpu2.yaml -c aci-wall600.yaml \
  -o "results/gemma-$condition"
```

문제당 600초이며 새 실행에는 새 출력 경로를 사용한다.
Qwen 설정은 `model-qwen35-27b.yaml`, `endpoint-gpu3.yaml`, `serve-qwen35-27b.yaml`이다.
가중치 경로는 `models/Qwen3.5-27B`, revision은 `fc05daec18b0a78c049392ed2e771dde82bdf654`이다.

## 데이터·채점·검사

기존 고정100 입력은 그대로 유지했다. [선택 기록](data/selection.json), 실행용
`data/agent/test.jsonl`, 공식 채점용 `data/evaluator/tasks.json`은 같은 100문제다.

```bash
uv run --locked --extra research python -m swebench.harness.run_evaluation \
  --dataset_name data/evaluator/tasks.json \
  --predictions_path "results/gemma-$condition/preds.json" \
  --run_id "e03-gemma-$condition" --max_workers 2 --timeout 900

uv run --locked --extra research pytest -q \
  tests/aci/test_configs.py tests/aci/test_related_tests.py tests/aci/test_verification_feedback.py
```

개발용 검사는 우리 실행·피드백 구현을 확인하며 벤치마크 채점과 별개다.
Docker replay에는 `ACI_NATIVE_REPLAY=1`과 `aci-lens-smoke:mini-20261025` 이미지가 필요하다.
CodeStruct 원본 대조 검사는 lock의 원본을 `external/CodeStruct`에 준비하고,
설치된 번들 경로를 `ACI_TEST_BUNDLES`로 지정한다.
