"""실행 흐름. 에피소드 하나 = 독립 메모리 scope 하나.

    for episode (작업 프로세스 --workers 개가 나눠 맡음):
        reset(scope, speakers)
        for session in episode.sessions:        ingest(scope, session)      ← 시간: ingest_seconds
        for question in episode.questions:
            retrieval = retrieve(scope, q, reference_date, top_k)           ← 시간: retrieve_seconds
            prediction = answerer(benchmark.answer_prompt(q, retrieval))    ← 시간: answer_seconds
            scores = {m: ... for m in eval_metrics}                         ← llm_judge / f1 / bleu1
            records.jsonl 에 한 줄 추가 (체크포인트)
        close(scope)

재개(--resume): records.jsonl 에 있는 question_id 는 건너뛴다. 적재 도중 끊긴 에피소드는
어댑터가 save_load 를 지원하면 저장본에서, 아니면 처음부터 다시 적재한다.
manifest(데이터 해시·어댑터 setup() 반환값·공통 평가 환경 설정)가 다르면 재개를 거부한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunConfig:
    algorithm: str
    benchmark: str
    variant: str
    eval_metrics: list[str]
    dataset: Path | None = None
    algorithm_python: Path | None = None
    seed: int = 42
    answer_mode: str = "harness"
    answer_model: str = "gpt-4o-mini"
    judge_model: str | None = None     # None → 벤치마크 기본값(LoCoMo gpt-4o-mini, LongMemEval gpt-4o-2024-08-06)
    top_k: int = 10
    workers: int = 4
    limit_episodes: int = 0
    max_questions: int = 0
    repeats: int = 1
    fake: bool = False
    resume: bool = False
    output_dir: Path = field(default_factory=lambda: Path("results"))


def run(cfg: RunConfig) -> int:
    raise NotImplementedError("TODO: 위 흐름 구현")
