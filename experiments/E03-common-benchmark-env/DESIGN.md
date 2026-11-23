# E03 설계 — 벤치마크 통일 평가 환경

코드는 `src/` 에 있다. 아래 명령은 모두 `src/` 에서 실행한다. 실행 절차는 [README.md](README.md), 실험 카드는 [CARD.md](CARD.md).

### 사용 예시
```bash
.venv/bin/python run.py --algorithm {아이디어1} --benchmark locomo
.venv/bin/python run.py --algorithm {아이디어2} --benchmark longmemeval --eval-metric LLM-as-a-judge F1
```

## 1. 설계 원칙

1. **알고리즘은 적재(ingest)·검색(retrieve)만 한다.** 답변 생성·채점·집계는 공통 평가 환경이 모든 알고리즘에
   같은 프롬프트·모델·top-k 로 한다. 
2. **정답 정보는 알고리즘에 가지 않는다.** 정답·카테고리·근거 표시(LoCoMo evidence, LongMemEval answer_session_ids/has_answer)는
   공통 평가 환경에만 둔다. `retrieve()` 인자에 카테고리가 없다.
3. **알고리즘마다 가상환경이 다르다.** 공통 평가 환경은 알고리즘 코드를 import 하지 않는다. 알고리즘은 자기 venv 의
   python 으로 띄운 작업 프로세스에서 돌고, 공통 평가 환경과 JSONL로 통신.
4. **독립 메모리 단위(scope)는 벤치마크가 정한다.** LoCoMo 는 대화 하나, LongMemEval 은 질문 하나.
5. **알고리즘 추가 = 폴더 하나 추가.** `algorithms/<name>/algorithm.toml` 을 공통 평가 환경이 자동으로 찾는다.

## 2. 가상환경 만들기
가상환경은 **알고리즘마다 1개**다. 모두 `scripts/setup_venv.sh` 한 줄로 만든다.

| 대상 | 위치 | 버전·의존성을 정하는 곳 |
|---|---|---|
| 공통 평가 환경 (`run.py`, 답변·judge·지표) | `src/.venv` | `requirements.txt` (Python 3.12 고정) |
| 알고리즘 `<name>` | `algorithms/<name>/.venv` | `algorithms/<name>/algorithm.toml` 의 `python`, `requirements` |

### 2.1 기본: 스크립트 한 줄

`src/` 에서 실행한다. [uv](https://docs.astral.sh/uv/) 가 필요하다
(`algorithm.toml` 에 적힌 파이썬 버전이 없으면 uv 가 내려받는다).

```bash
scripts/setup_venv.sh {알고리즘1}
```

알고리즘 이름을 주면 스크립트가 차례로 한다.

1. `algorithms/<name>/algorithm.toml` 에서 `python`, `venv`, `requirements` 를 읽는다.
2. venv 가 없을 때만 `uv venv --python <버전>` 으로 만든다.
3. `uv pip install -r <requirements>` 로 의존성을 설치한다.

### 2.2 새 알고리즘의 가상환경

```
algorithms/알고리즘1/
|── .venv
├── algorithm.toml      name · adapter · python · requirements (§4.2)
├── adapter.py          MemoryAdapter 상속 (§4.1)
├── requirements.txt    이 알고리즘만의 의존성
└── setup.sh            (선택) venv 생성 전 준비 — 원본 코드 clone·커밋 고정·모델 다운로드 등
```

## 3. 구성

```
src/
├── run.py                      진입점 (--algorithm --benchmark --eval-metric ...)
├── requirements.txt            공통 평가 환경 venv 의존성 (openai, nltk, tiktoken)
├── scripts/setup_venv.sh       venv 생성: <algorithm>
├── adapter_sdk/                알고리즘 venv 쪽 SDK — 표준 라이브러리만 사용
│   ├── types.py                Turn · Session · Item · Retrieval (주고받는 데이터)
│   ├── adapter.py              MemoryAdapter 인터페이스
│   └── serve.py                작업 프로세스 (JSON Lines 서버)
├── harness/                    공통 평가 환경 venv 쪽
│   ├── registry.py             algorithms/*/algorithm.toml 읽기
│   ├── worker.py               알고리즘 작업 프로세스 띄우기·호출        (동작)
│   ├── schema.py               Episode · Question
│   ├── runner.py               실행 흐름·병렬·체크포인트·재개           (TODO)
│   ├── answer.py · judge.py    공통 답변기 · LLM-as-a-judge         (TODO)
│   ├── metrics.py              F1 · BLEU-1 · 집계                 (TODO)
│   └── report.py               결과 파일·알고리즘 비교표               (TODO)
├── benchmarks/                 벤치마크 규약 (로더·답변 프롬프트·judge 프롬프트·카테고리)
│   ├── base.py                 Benchmark 인터페이스
│   ├── locomo.py               (TODO: 로더·프롬프트 이식)
│   └── longmemeval.py          (TODO: 로더·프롬프트 이식)
├── algorithms/
│   └── example/                배선 확인용 예시 (API 없음). 새 알고리즘은 이 폴더를 복사해 시작
└── tests/                      API 없는 어댑터 통신 테스트
결과: ../results/pilot/<benchmark>/<algorithm>/<run_id>/
```



- **어댑터 SDK 는 설치하지 않는다.** 공통 평가 환경이 작업 프로세스를 띄울 때 `PYTHONPATH=src/` 로 `adapter_sdk` 를 넘긴다.
  SDK 는 표준 라이브러리만 쓰므로 Python 3.10 이상 어느 venv 에서도 올라간다.
- **원본 저장소의 requirements 를 그대로 쓰려면** 이 폴더의 `requirements.txt` 에 `-r <원본 경로>/requirements.txt` 한 줄을
  적는다(외부 저장소를 감싸는 알고리즘). 경로는 그 requirements 파일 기준 상대경로다.
- **버전 고정**: 첫 설치가 끝나면 그 venv 에서 `uv pip freeze` 한 결과를 `requirements.txt` 에 옮겨 재현성을 확보한다.
- 공통 평가 환경 venv 에는 알고리즘 의존성을 넣지 않는다. 공통 평가 환경은 알고리즘 코드를 import 하지 않기 때문이다.

## 4. 알고리즘 어댑터

### 4.1 인터페이스 (`adapter_sdk/adapter.py`)

| 메서드 | 필수 | 하는 일 |
|---|---|---|
| `setup(config) → dict` | | 1회 초기화. 반환값(버전·모델·하이퍼파라미터)이 결과 manifest 에 기록된다 |
| `reset(scope, speakers)` | 필수 | 빈 메모리로 scope 를 연다 |
| `ingest(scope, session)` | 필수 | 세션 하나 적재. 몇 턴씩 묶을지·화자별로 나눌지는 알고리즘이 정한다 |
| `retrieve(scope, question, reference_date, top_k) → Retrieval` | 필수 | `items`(텍스트·시각·점수·owner) 또는 `context`(문자열) |
| `usage() → dict` | | 누적 LLM·임베딩 호출과 토큰 → 비용 집계 |
| `answer(...)` | | 고유 답변기 (`capabilities` 에 `native_answer`) |
| `save(scope, path)` / `load(scope, path)` | | 적재 결과 저장·복원 (`save_load`). 재개, 같은 메모리로 답변·judge 만 바꾸는 실험에 쓴다 |
| `close(scope)` | | 메모리 해제 |


### 4.2 `algorithm.toml`

```toml
name = "idea1"
adapter = "algorithms.idea1.adapter:Idea1Adapter"
source = "../../vendor/some-memory"  # 감쌀 원본 코드 (선택) → setup(config["source"]) 에 절대경로로 전달
python = "3.11"
venv = ""                             # 비우면 이 폴더의 .venv, 기존 환경은 경로로 지정
requirements = "requirements.txt"
capabilities = ["native_answer"]
[config]                              # setup(config) 로 그대로 전달
model = "gpt-4o-mini"
```

## 5. 지표

### 5.1 정답 지표 — `--eval-metric` (여러 개, 옵션 반복 가능, 기본 전부)

| 값 (별칭) | 정의 | 출처 |
|---|---|---|
| `llm_judge` (LLM-as-a-judge, judge) | 정답/오답 이진 판정 평균 | 프롬프트는 벤치마크 원본(§5.3), 모델은 `--judge-model` 로 통일 |
| `f1` (F1) | `set(simple_tokenize)` 토큰 F1 | mem0-evaluation `metrics/utils.py` (SQuAD F1 아님) |
| `bleu1` (BLEU, BLEU-1, blue) | `nltk.word_tokenize` + `sentence_bleu(weights=(1,0,0,0), method1)` | 같은 출처 |

내부 값은 0..1, 표에서는 %. 전체 점수는 문항 평균(micro)이고 카테고리 점수의 단순 평균이 아니다.
`--repeats N` 이면 반복별 점수의 평균 ± 표본 SD.

### 5.2 효율 지표 

| 지표 | 의미 |
|---|---|
| `ingest_seconds` (총·턴당) | 메모리 구축 시간 |
| `retrieve_seconds` p50/p95 | 검색 지연 (어댑터 안에서 잰 값) |
| `answer_seconds` p50/p95 | 공통 답변기 지연 |
| `context_tokens_mean` | 답변 프롬프트에 넣은 메모리 문맥 토큰 (cl100k_base) |
| `memory_usage` / `answer_usage` / `judge_usage` | LLM·임베딩 호출 수와 토큰 |
| `cost_usd` | 위 사용량 × 단가 (추정치, 실제 청구는 콘솔) |

### 5.3 벤치마크별 고정 규약

| | LoCoMo | LongMemEval |
|---|---|---|
| scope | 대화 (10개) | 질문 (500개) |
| 변형 | `locomo10` | `longmemeval_s_cleaned`(기본) · `longmemeval_oracle` · `longmemeval_m_cleaned` |
| 평가 문항 | cat1–4 1,540 (cat5 기본 제외) | 500 (abstention `_abs` 포함) |
| 카테고리 키 | 정수 번호 문자열 `"1"`–`"5"` (라벨 드리프트 방지) | `question_type` 원문 |
| 답변 프롬프트 | 공통 1종 (화자별 owner 가 있으면 mem0-evaluation 형식으로 묶음) — **확정 필요** | 공식 no-CoT |
| judge 프롬프트 | mem0-evaluation `ACCURACY_PROMPT` | 공식 유형별 5종 + abstention |
| judge 기본 모델 | gpt-4o-mini | gpt-4o-2024-08-06 (공식) |
| reference_date | 없음 | `question_date` |

## 6. 결과 형식 (예정)

```
results/pilot/<benchmark>/<algorithm>/<run_id>/
  manifest.json   설정·데이터 해시·어댑터 setup() 반환값·패키지 버전 (재개 검증)
  records.jsonl   문항별 질문·정답·예측·검색 결과·지표·시간·토큰
  summary.json    overall · by_category · efficiency (모든 알고리즘이 같은 스키마)
  summary.md
  adapter.log     알고리즘 작업 프로세스 stderr
```