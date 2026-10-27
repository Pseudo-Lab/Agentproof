"""LoCoMo-10. 대화 하나 = Episode 하나 (10개), cat1–4 1,540문항 (cat5 기본 제외).

참고·이식 대상:
  로더   memodb-io/memobase@358c16b docs/experiments/locomo-benchmark/src/memzero/add.py (세션 키 필터, 날짜, 화자별 적재)
         mem0ai/memory-benchmarks@4b61c5d benchmarks/locomo/run.py (공식 러너의 적재 형식)
  judge  memodb-io/memobase@358c16b docs/experiments/locomo-benchmark/metrics/llm_judge.py ACCURACY_PROMPT (mem0-evaluation 원본)
보존할 원본 정보: sample_id, qa 인덱스(question_id = "conv-26:12"), dia_id(Turn.turn_id), 화자, 세션 날짜,
이미지 caption(blip_caption, 발화 text 에 덧붙일지 결정 필요).
"""

from __future__ import annotations

from pathlib import Path

from adapter_sdk.types import Retrieval
from harness.schema import Episode, Question

from .base import Benchmark

DATA = Path(__file__).resolve().parents[2] / "data" / "raw"   # <실험>/data/raw (data/README.md 로 내려받는다)


class LoCoMo(Benchmark):
    name = "locomo"
    scope_unit = "conversation"
    variants = ("locomo10",)
    default_judge_model = "gpt-4o-mini"
    categories = {"1": "multi-hop", "2": "temporal", "3": "open-domain", "4": "single-hop", "5": "adversarial"}
    excluded_categories = ("5",)

    @classmethod
    def dataset_path(cls, variant: str) -> Path:
        return DATA / f"{variant}.json"

    def load(self, path: Path) -> list[Episode]:
        raise NotImplementedError("TODO: 원본 JSON → Episode(speakers=[speaker_a, speaker_b])")

    def answer_prompt(self, question: Question, retrieval: Retrieval) -> str:
        # 모든 알고리즘에 같은 템플릿. Item.owner 가 있으면 화자별로 묶어 mem0-evaluation ANSWER_PROMPT 형식,
        # 없으면 같은 지시문에 단일 목록. retrieval.context 가 있으면 그것을 그대로 넣는다.
        raise NotImplementedError("TODO")

    def judge_prompt(self, question: Question, prediction: str) -> str:
        raise NotImplementedError("TODO: ACCURACY_PROMPT.format(question, gold_answer, generated_answer)")
