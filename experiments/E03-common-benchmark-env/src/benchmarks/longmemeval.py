"""LongMemEval. 질문 하나 = Episode 하나 (질문마다 자기 대화 기록 haystack 을 별도 scope 에 적재).

변형: longmemeval_s_cleaned(기본, 질문당 세션 약 50개·약 115k 토큰) · longmemeval_oracle(근거 세션만, 배선 확인용)
      · longmemeval_m_cleaned(질문당 약 500세션, 비용 큼)
데이터: <실험>/data/raw/<variant>.json (data/README.md)
참고·이식 대상:
  xiaowu0162/LongMemEval@9e0b455 src/generation/run_generation.py — 공식 no-CoT 답변 프롬프트
  xiaowu0162/LongMemEval@9e0b455 src/evaluation/evaluate_qa.py    — 질문 유형별 judge 5종 + abstention
  mem0ai/memory-benchmarks@4b61c5d benchmarks/longmemeval/run.py, prompts.py — 공식 러너 비교용
보존: haystack_session_ids/dates, question_date(→ Question.reference_date), question_type, abstention(_abs).
answer_session_ids·has_answer 는 평가(근거 회수율)용이며 알고리즘 프로세스에 넘기지 않는다.
judge 기본 모델은 공식 평가와 같은 gpt-4o-2024-08-06.
"""

from __future__ import annotations

from pathlib import Path

from adapter_sdk.types import Retrieval
from harness.schema import Episode, Question

from .base import Benchmark

DATA = Path(__file__).resolve().parents[2] / "data" / "raw"   # <실험>/data/raw (data/README.md 로 내려받는다)


class LongMemEval(Benchmark):
    name = "longmemeval"
    scope_unit = "question"
    variants = ("longmemeval_s_cleaned", "longmemeval_oracle", "longmemeval_m_cleaned")
    default_judge_model = "gpt-4o-2024-08-06"
    categories = {t: t for t in ("single-session-user", "single-session-assistant", "single-session-preference",
                                 "multi-session", "knowledge-update", "temporal-reasoning")}

    @classmethod
    def dataset_path(cls, variant: str) -> Path:
        return DATA / f"{variant}.json"

    def load(self, path: Path) -> list[Episode]:
        raise NotImplementedError("TODO: 원본 JSON → Episode(speakers=['user', 'assistant'])")

    def answer_prompt(self, question: Question, retrieval: Retrieval) -> str:
        raise NotImplementedError("TODO: run_generation.py 공식 no-CoT 프롬프트")

    def judge_prompt(self, question: Question, prediction: str) -> str:
        raise NotImplementedError("TODO: evaluate_qa.py judge 프롬프트 (category 가 _abs 로 끝나면 abstention)")
