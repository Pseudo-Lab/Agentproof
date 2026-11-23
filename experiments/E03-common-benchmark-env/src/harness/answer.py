"""공통 답변 생성. 모든 알고리즘에 같은 모델·프롬프트(벤치마크가 정한 것)를 쓴다.

--answer-mode harness (기본): Retrieval → benchmark.answer_prompt() → answer_model 호출
--answer-mode native        : 어댑터 answer() 결과를 그대로 쓴다 (capabilities 에 native_answer 필요).
                              통일 비교표에는 넣지 않고 따로 표시한다.
"""

from __future__ import annotations


class Answerer:
    def __init__(self, model: str, fake: bool = False):
        self.model, self.fake = model, fake

    def __call__(self, prompt: str) -> str:
        raise NotImplementedError("TODO: OpenAI chat 호출 (temperature 0), 사용량 집계, 감사 로그")
