"""LLM-as-a-judge. 프롬프트는 벤치마크가 정하고(원본 그대로), 모델은 --judge-model 로 통일한다.

  LoCoMo      mem0-evaluation ACCURACY_PROMPT (memodb-io/memobase@358c16b docs/experiments/locomo-benchmark/metrics/llm_judge.py)
  LongMemEval 공식 질문 유형별 프롬프트 5종 + abstention (xiaowu0162/LongMemEval@9e0b455 src/evaluation/evaluate_qa.py)
"""

from __future__ import annotations


class Judge:
    def __init__(self, model: str, fake: bool = False):
        self.model, self.fake = model, fake

    def __call__(self, prompt: str) -> int:
        """1(정답) / 0(오답). 응답 파싱 실패는 예외로 올려 재개 시 다시 채점한다."""
        raise NotImplementedError("TODO")
