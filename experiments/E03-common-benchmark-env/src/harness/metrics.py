"""통일 지표. --eval-metric 으로 고른 정답 지표 + 항상 기록하는 효율 지표.

정답 지표 (--eval-metric, 여러 개 가능, 기본 전부):
  llm_judge  LLM-as-a-judge 정답률(0..1) — 프롬프트는 벤치마크별 원본(judge.py)
  f1         토큰 F1(0..1) — mem0-evaluation utils.py 정의 (set(simple_tokenize))
  bleu1      BLEU-1(0..1)  — 같은 출처, nltk.word_tokenize + method1 smoothing
  원본 구현: memodb-io/memobase@358c16b docs/experiments/locomo-benchmark/metrics/utils.py (simple_tokenize, calculate_metrics)

효율 지표 (항상):
  ingest_seconds_per_turn, retrieve_seconds p50/p95, answer_seconds p50/p95,
  context_tokens_mean(cl100k_base), memory_usage(어댑터 보고), answer_usage, judge_usage, cost_usd
"""

from __future__ import annotations

from typing import Callable

EVAL_METRICS = ("llm_judge", "f1", "bleu1")


def token_f1(prediction: str, reference: str) -> float:
    raise NotImplementedError("TODO: metrics/utils.py F1 이식")


def bleu1(prediction: str, reference: str) -> float:
    raise NotImplementedError("TODO: metrics/utils.py BLEU-1 이식")


# llm_judge 는 judge 클라이언트가 필요해 runner 가 따로 부른다.
LEXICAL: dict[str, Callable[[str, str], float]] = {"f1": token_f1, "bleu1": bleu1}


def aggregate(records: list[dict], metrics: list[str]) -> dict:
    """문항 기록 → {overall, by_category, efficiency}. 전체 점수는 문항별 산술평균.
    반복(--repeats) 간 점수는 반복별 점수의 평균 ± 표본 SD(ddof=1)."""
    raise NotImplementedError("TODO")
