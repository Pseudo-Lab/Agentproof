# E03 실행 안내 — 공통 벤치마크 테스트 환경

메모리 저장 알고리즘을 LoCoMo·LongMemEval 에서 **같은 답변기·judge·지표**로 비교하기 위한 평가 환경이다.
설계는 [DESIGN.md](DESIGN.md), 연구 질문·현재 상태는 [CARD.md](CARD.md).

**현재 상태: 설계·뼈대 단계, 모델 호출 없음.** 동작하는 것은 설정 확인(`--list`, `--dry-run`)과
공통 평가 환경 ↔ 알고리즘 작업 프로세스 통신(테스트)이다. 데이터 로더·답변·채점·집계는 TODO 이며,
`--dry-run` 없이 평가를 실행하면 "아직 뼈대 단계"로 종료한다(exit 2). `results/pilot/` 에 결과는 아직 없다.

## 요구 사항

- Python 3.11+ (`--list`·`--dry-run`·테스트는 표준 라이브러리만 사용)
- 실제 평가를 돌릴 때: [uv](https://docs.astral.sh/uv/) (가상환경 생성), 환경 변수 `OPENAI_API_KEY` (답변·judge, 알고리즘에 따라 메모리 구축).
  키는 로컬 `.env`·셸에만 두고 커밋하지 않는다. 알고리즘마다 추가 키가 필요할 수 있다(각 `algorithm.toml` 에 명시).

## 확인 명령 (API 호출 없음)

실험 폴더(`experiments/E03-common-benchmark-env/`)의 `src/` 에서 실행한다.

```sh
cd experiments/E03-common-benchmark-env/src
python3 -m unittest discover -s tests -v
python3 run.py --list
python3 run.py --algorithm example --benchmark locomo --eval-metric F1 LLM-as-a-judge --dry-run
```

- 테스트: `example` 어댑터를 작업 프로세스로 띄워 setup·reset·ingest·retrieve 왕복, 어댑터 오류 전달과 프로세스 유지 확인
- `--dry-run`: 해석된 설정, 알고리즘 venv·데이터 파일 존재 여부, 지표 규약, 출력 위치를 JSON 으로 출력 (파일·API 없음)

## 가상환경 (알고리즘마다 따로)

```sh
scripts/setup_venv.sh harness
scripts/setup_venv.sh example
```

공통 평가 환경은 `src/.venv`, 알고리즘은 `src/algorithms/<name>/.venv` 에 만든다. 자세한 내용은 [DESIGN.md §2](DESIGN.md).

## 데이터

[data/README.md](data/README.md) 의 명령으로 `data/raw/` 에 받는다(커밋하지 않음). 출처·버전·체크섬·사용 조건이 적혀 있다.

## 평가 실행 (구현 후)

```sh
.venv/bin/python run.py --algorithm <name> --benchmark locomo --eval-metric LLM-as-a-judge F1 BLEU
.venv/bin/python run.py --compare ../results/pilot/locomo
```

결과는 `results/pilot/<benchmark>/<algorithm>/<run_id>/` 에 `manifest.json`·`records.jsonl`·`summary.json` 으로 남긴다
(같은 run ID 는 덮어쓰지 않는다). 실제 실행 전에 호출 대상 모델과 예상 비용을 CARD 에 먼저 적는다.
