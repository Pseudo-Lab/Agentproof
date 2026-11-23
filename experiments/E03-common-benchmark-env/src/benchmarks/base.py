"""벤치마크 규약: 데이터 → Episode, 답변 프롬프트, judge 프롬프트, 카테고리 이름.

벤치마크마다 다른 것은 여기서만 정한다. 알고리즘은 이 내용을 모른다.
정답·근거(evidence/has_answer)·카테고리는 공통 평가 환경에만 두고 ingest/retrieve 입력에 넣지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from adapter_sdk.types import Retrieval
from harness.schema import Episode, Question


class Benchmark(ABC):
    name: str = "base"
    scope_unit: str = ""                       # 독립 메모리 단위: "conversation" / "question"
    variants: tuple[str, ...] = ()             # 첫 번째가 기본값
    default_judge_model: str = "gpt-4o-mini"
    categories: dict[str, str] = {}            # 카테고리 키 → 표시 이름
    excluded_categories: tuple[str, ...] = ()  # 기본 집계에서 뺄 카테고리

    @classmethod
    @abstractmethod
    def dataset_path(cls, variant: str) -> Path:
        """--dataset 을 주지 않았을 때 쓸 원본 JSON 경로."""

    @abstractmethod
    def load(self, path: Path) -> list[Episode]:
        """데이터를 읽어 Episode 목록으로 바꾼다. 세션은 시간 순서, 질문은 원래 순서."""

    @abstractmethod
    def answer_prompt(self, question: Question, retrieval: Retrieval) -> str:
        """공통 평가 환경의 답변기에 넣을 프롬프트. 모든 알고리즘에 같은 템플릿을 쓴다."""

    @abstractmethod
    def judge_prompt(self, question: Question, prediction: str) -> str:
        """LLM-as-a-judge 프롬프트 (원본 그대로)."""
